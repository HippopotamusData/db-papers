#!/usr/bin/env bash

set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PYTHON=${PYTHON:-python3}
target_paper_id=${PAPER_ID:-}
deep_validation=${DEEP_VALIDATION:-0}

if [[ "$deep_validation" != "0" && "$deep_validation" != "1" ]]; then
  echo "ERROR: DEEP_VALIDATION must be 0 or 1" >&2
  exit 1
fi

failures=0
warnings=0
record_count=0
translation_count=0
translation_file_count=0

fail() {
  echo "ERROR: $*" >&2
  failures=$((failures + 1))
}

warn() {
  echo "WARNING: $*" >&2
  warnings=$((warnings + 1))
}

quality_issue() {
  if [[ "${quality_severity:-}" == "warning" ]]; then
    warn "$*"
  else
    fail "$*"
  fi
}

has_waiver() {
  local waiver_list=$1
  local expected=$2
  [[ $'\t'"$waiver_list"$'\t' == *$'\t'"$expected"$'\t'* ]]
}

for command_name in rg pdfinfo pdftotext perl sed awk find sort mktemp; do
  command -v "$command_name" >/dev/null 2>&1 || fail "required command is unavailable: $command_name"
done

if ! "$PYTHON" --version >/dev/null 2>&1; then
  fail "configured Python is unavailable: $PYTHON"
fi

(( failures == 0 )) || exit 1
if [[ "${SKIP_METADATA_VALIDATION:-0}" != "1" ]]; then
  metadata_args=(validate)
  [[ -n "$target_paper_id" ]] && metadata_args+=(--paper-id "$target_paper_id")
  "$PYTHON" scripts/papers.py "${metadata_args[@]}" || exit 1
fi
manifest=$(mktemp "${TMPDIR:-/tmp}/db-papers-validation-manifest.XXXXXX")
trap 'rm -f "$manifest"' EXIT
manifest_args=(validation-manifest)
[[ -n "$target_paper_id" ]] && manifest_args+=(--paper-id "$target_paper_id")
"$PYTHON" scripts/papers.py "${manifest_args[@]}" > "$manifest" || exit 1

{
IFS=$'\x1f' read -r manifest_kind source_name translation_name require_complete_references allow_whole_page_images
[[ "$manifest_kind" == "config" ]] || {
  fail "validation manifest is missing its config row"
  exit 1
}

while IFS=$'\x1f' read -r manifest_kind dir reading_status paper_page_limit acceptance_waivers skip_reason paper_title quality_severity; do
  [[ "$manifest_kind" == "paper" ]] || {
    fail "validation manifest contains an invalid row"
    continue
  }
  paper_id=${dir##*/}
  record_count=$((record_count + 1))
  pdf="$dir/$source_name"
  translation="$dir/$translation_name"

  case "$reading_status" in
    unavailable)
      [[ ! -f "$pdf" ]] || fail "$dir is unavailable but source.pdf exists"
      [[ ! -f "$translation" ]] || fail "$dir is unavailable but translation.md exists"
      continue
      ;;
    source_only|skipped)
      [[ -f "$pdf" ]] || fail "$dir has reading_status=$reading_status but source.pdf is missing"
      [[ ! -f "$translation" ]] || fail "$dir has reading_status=$reading_status but translation.md exists"
      if [[ -f "$pdf" ]]; then
        pages=$(pdfinfo "$pdf" 2>/dev/null | awk '/^Pages:/{print $2}')
        [[ -n "$pages" ]] || fail "$pdf is unreadable"
        if [[ -n "$pages" ]] && [[ "$reading_status" == "source_only" ]] && (( pages > paper_page_limit )); then
          fail "$dir is source_only but exceeds its page limit ($pages pages; limit=$paper_page_limit); use skipped or an explicit exception"
        fi
        if [[ -n "$pages" ]] && [[ "$reading_status" == "skipped" ]]; then
          if [[ "$skip_reason" == "over-page-limit" ]] && (( pages <= paper_page_limit )); then
            fail "$dir has skipped reason over-page-limit but now fits policy ($pages pages; limit=$paper_page_limit); review policy status"
          fi
        fi
      fi
      continue
      ;;
    draft)
      translation_file_count=$((translation_file_count + 1))
      [[ -f "$translation" ]] || fail "$dir is draft but translation.md is missing"
      [[ -f "$pdf" ]] || fail "$dir is draft but source.pdf is missing"
      ;;
    translated)
      translation_count=$((translation_count + 1))
      translation_file_count=$((translation_file_count + 1))
      [[ -f "$translation" ]] || fail "$dir is translated but translation.md is missing"
      [[ -f "$pdf" ]] || fail "$dir is translated but source.pdf is missing"
      ;;
    *)
      fail "$dir has invalid reading_status: $reading_status"
      continue
      ;;
  esac

  [[ -f "$translation" ]] || continue

  fence_count=$(rg -c '^```' "$translation" 2>/dev/null || true)
  (( fence_count % 2 == 0 )) || fail "$translation has unbalanced fenced code blocks"

  if [[ "$allow_whole_page_images" == "false" ]] && rg -q -i '!\[[^]]*\]\([^)]*(original-)?page[-_ ]?[0-9]|整页截图' "$translation"; then
    quality_issue "$translation contains a whole-page screenshot"
  fi

  if rg -q -i '覆盖索引|图像资源索引|仍需人工确认|未嵌入项|contact[ -]?sheet|crop candidate|rework log|本轮|视觉确认|PDF[[:space:]]*抽取|请结合[^。\n]*source\.pdf[^。\n]*(补齐|还原)|QA[[:space:]]*(记录|说明|残留)' "$translation"; then
    quality_issue "$translation contains review or workflow residue"
  fi

  if rg -q '^#{1,4} .*(还原覆盖|公式覆盖说明|步骤保留|表格转写|图表、公式与代码清单|公式与算法自检)' "$translation"; then
    quality_issue "$translation contains workflow-style headings"
  fi

  if rg -q -i '(^|[^[:alpha:]])(TODO|FIXME|TBD)([^[:alpha:]]|$)|待补译|待返工|仍需补充|人工确认后通过' "$translation"; then
    quality_issue "$translation contains unfinished-work markers"
  fi

  if rg -q '^[[:space:]]*[0-9]+\.[[:space:]]+\[[0-9]+\]' "$translation"; then
    quality_issue "$translation contains double-numbered references"
  fi

  narrative_issues=$("$PYTHON" scripts/validate_narrative_voice.py "$translation")
  narrative_status=$?
  if (( narrative_status == 1 )); then
    quality_issue "$translation contains ambiguous bare-author narration: $narrative_issues"
  elif (( narrative_status != 0 )); then
    fail "$translation narrative-voice validation failed (exit=$narrative_status)"
  fi

  h1=$(awk '/^# /{print; exit}' "$translation")
  [[ "$h1" == "# ${paper_title}（中文译文）" ]] || quality_issue "$translation H1 must exactly match paper.yaml title plus （中文译文）"
  rg -q '^## 译者说明$' "$translation" || quality_issue "$translation is missing the standard translator-note heading"
  rg -q '^本文依据同目录的 `source\.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。$' "$translation" || quality_issue "$translation is missing the standard translator-note sentence"

  duplicate_images=$(rg -o '!\[[^]]*\]\([^)]*\)' "$translation" 2>/dev/null | sed -E 's/^.*\(([^)]+)\)$/\1/' | sort | uniq -d)
  [[ -z "$duplicate_images" ]] || quality_issue "$translation contains duplicate image references: $duplicate_images"

  broken_images=$(perl -MFile::Basename=dirname -MFile::Spec -ne '
    while (/!\[[^\]]*\]\((<[^>]+>|[^)[:space:]]+)/g) {
      $path = $1;
      $path =~ s/^<|>$//g;
      next if $path =~ m{^(https?:|data:)};
      $full = File::Spec->rel2abs($path, dirname($ARGV));
      print "$path\n" unless -e $full;
    }
  ' "$translation")
  [[ -z "$broken_images" ]] || quality_issue "$translation has broken image references: $broken_images"

  if [[ "$deep_validation" != "1" ]]; then
    if [[ "$reading_status" == "draft" ]]; then
      pages=$(pdfinfo "$pdf" 2>/dev/null | awk '/^Pages:/{print $2}')
      [[ -n "$pages" ]] || fail "$pdf is unreadable"
      if [[ -n "$pages" ]] && (( pages > paper_page_limit )); then
        fail "$translation exists for over-limit PDF ($pages pages; limit=$paper_page_limit)"
      fi
    fi
    continue
  fi

  pages=$(pdfinfo "$pdf" 2>/dev/null | awk '/^Pages:/{print $2}')
  [[ -n "$pages" ]] || fail "$pdf is unreadable"
  if [[ -n "$pages" ]] && (( pages > paper_page_limit )); then
    fail "$translation exists for over-limit PDF ($pages pages; limit=$paper_page_limit)"
  fi

  source_text=$(mktemp "${TMPDIR:-/tmp}/db-papers-pdftext.XXXXXX")
  if ! pdftotext -layout "$pdf" "$source_text" 2>/dev/null; then
    fail "$pdf text extraction failed"
  else
    listing_issues=$("$PYTHON" scripts/validate_listings.py "$source_text" "$translation")
    listing_status=$?
    if (( listing_status != 0 )); then
      if (( listing_status == 1 )); then
        quality_issue "$translation has deterministic source-listing errors: $listing_issues"
      elif (( listing_status == 3 )); then
        if [[ "$reading_status" == "translated" ]] && has_waiver "$acceptance_waivers" "listings"; then
          echo "REVIEWED-RISK: $translation Listing candidates were manually disposed in acceptance ledger"
        elif [[ "$reading_status" == "draft" ]]; then
          warn "$translation has Listing review candidates: $listing_issues"
        else
          fail "$translation has unresolved Listing review candidates (record disposition before acceptance): $listing_issues"
        fi
      else
        fail "$translation listing validation failed (exit=$listing_status)"
      fi
    fi

    source_chars=$(tr -d '[:space:]' < "$source_text" | wc -m | tr -d ' ')
    translated_chars=$(sed '/^!\[/d;/^---$/d;/^[a-z_]*:/d' "$translation" | tr -d '[:space:]' | wc -m | tr -d ' ')
    if awk -v s="$source_chars" -v t="$translated_chars" 'BEGIN { exit !(s > 0 && t / s < 0.25) }'; then
      quality_issue "$translation has suspiciously low source/translation coverage ($translated_chars/$source_chars)"
    fi

    source_words=$(pdftotext -raw "$pdf" - 2>/dev/null | perl -CSD -ne 'last if /^\s*(?:\d+\.?\s+)?REFERENCES\s*$/i; $n += () = /\b[A-Za-z]+(?:[-'"'"'][A-Za-z]+)*\b/g; END { print $n + 0 }')
    translated_cjk=$(perl -CSD -ne 'last if /^##\s*(?:参考文献|References)\s*$/i; $n += () = /[\x{3400}-\x{9fff}]/g; END { print $n + 0 }' "$translation")
    if awk -v s="$source_words" -v t="$translated_cjk" 'BEGIN { exit !(s > 0 && t / s < 0.50) }'; then
      if [[ "$reading_status" == "translated" ]] && has_waiver "$acceptance_waivers" "abridgement"; then
        echo "REVIEWED-RISK: $translation high mechanical abridgement candidate was manually disposed in acceptance ledger"
      elif [[ "$reading_status" == "draft" ]]; then
        warn "$translation has high mechanical abridgement risk: CJK/source-word ratio=$translated_cjk/$source_words (<0.50)"
      else
        fail "$translation has unresolved high mechanical abridgement risk (record disposition before acceptance): CJK/source-word ratio=$translated_cjk/$source_words (<0.50)"
      fi
    elif awk -v s="$source_words" -v t="$translated_cjk" 'BEGIN { exit !(s > 0 && t / s < 0.75) }'; then
      if [[ "$reading_status" == "translated" ]] && has_waiver "$acceptance_waivers" "abridgement"; then
        echo "REVIEWED-RISK: $translation moderate mechanical abridgement candidate was manually disposed in acceptance ledger"
      elif [[ "$reading_status" == "draft" ]]; then
        warn "$translation has moderate abridgement risk: CJK/source-word ratio=$translated_cjk/$source_words (<0.75)"
      else
        fail "$translation has unresolved moderate abridgement risk (record disposition before acceptance): CJK/source-word ratio=$translated_cjk/$source_words (<0.75)"
      fi
    fi

    source_table_numbers=$(perl -ne 'while (/(?:^|\s{2,})Table\s+(\d+)\s*[:.]/ig) { print "$1\n" }' "$source_text" | sort -nu)
    while IFS= read -r table_number; do
      [[ -z "$table_number" ]] && continue
      rg -q "(表|Table)[[:space:]]*${table_number}([^0-9]|$)" "$translation" || quality_issue "$translation does not identify source Table $table_number"
    done <<< "$source_table_numbers"

    resource_args=("$dir" "$source_text")
    [[ "$require_complete_references" == "true" ]] && resource_args+=(--require-complete-references)
    [[ "$allow_whole_page_images" == "true" ]] && resource_args+=(--allow-whole-page-images)
    resource_issues=$("$PYTHON" scripts/validate_resources.py "${resource_args[@]}")
    resource_status=$?
    if (( resource_status == 1 )); then
      quality_issue "$translation has deterministic resource/reference errors: $resource_issues"
    elif (( resource_status == 3 )); then
      if [[ "$reading_status" == "translated" ]] && has_waiver "$acceptance_waivers" "resources"; then
        echo "REVIEWED-RISK: $translation resource candidates were manually disposed in acceptance ledger"
      elif [[ "$reading_status" == "draft" ]]; then
        warn "$translation has resource review candidates: $resource_issues"
      else
        fail "$translation has unresolved resource review candidates (record disposition before acceptance): $resource_issues"
      fi
    elif (( resource_status != 0 )); then
      fail "$translation resource validation failed (exit=$resource_status): $resource_issues"
    fi
  fi
  rm -f "$source_text"
done
} < "$manifest"

if [[ -n "$target_paper_id" ]] && (( record_count == 0 )); then
  fail "requested PAPER_ID was not found: $target_paper_id"
fi

if [[ -z "$target_paper_id" ]]; then
  filesystem_translation_count=$(find papers -type f -name translation.md | wc -l | tr -d ' ')
  [[ "$filesystem_translation_count" -eq "$translation_file_count" ]] || fail "reading statuses differ from translation files: statuses=$translation_file_count files=$filesystem_translation_count"
fi

if (( failures > 0 )); then
  echo "Validation failed with $failures error(s)." >&2
  exit 1
fi

if [[ "$deep_validation" == "1" ]]; then
  echo "Deep translation validation passed: $record_count records and $translation_count translated papers ($warnings warning(s))."
else
  echo "Fast translation validation passed: $record_count records and $translation_count translated papers ($warnings warning(s))."
fi
