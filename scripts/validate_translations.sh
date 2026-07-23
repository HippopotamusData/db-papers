#!/usr/bin/env bash

set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PYTHON=${PYTHON:-python3}
target_paper_id=
deep_validation=${DEEP_VALIDATION:-0}
acceptance_discovery=0
acceptance_evidence_file=
acceptance_paper_id=
acceptance_target_status=
acceptance_recorded_waivers=

for internal_name in ACCEPTANCE_DISCOVERY ACCEPTANCE_EVIDENCE_FILE ACCEPTANCE_PAPER_ID ACCEPTANCE_RECORDED_WAIVERS ACCEPTANCE_TARGET_STATUS PAPER_ID SKIP_METADATA_VALIDATION; do
  if [[ -n "${!internal_name+x}" ]]; then
    echo "ERROR: $internal_name is an internal preflight option, not an ambient environment interface" >&2
    exit 1
  fi
done

while (( $# > 0 )); do
  case "$1" in
    --paper-id)
      if (( $# < 2 )); then
        echo "ERROR: --paper-id requires a value" >&2
        exit 1
      fi
      target_paper_id=$2
      shift 2
      ;;
    --acceptance-discovery)
      acceptance_discovery=1
      shift
      ;;
    --acceptance-evidence-file|--acceptance-paper-id|--acceptance-target-status|--acceptance-recorded-waivers)
      if (( $# < 2 )); then
        echo "ERROR: $1 requires a value" >&2
        exit 1
      fi
      case "$1" in
        --acceptance-evidence-file) acceptance_evidence_file=$2 ;;
        --acceptance-paper-id) acceptance_paper_id=$2 ;;
        --acceptance-target-status) acceptance_target_status=$2 ;;
        --acceptance-recorded-waivers) acceptance_recorded_waivers=$2 ;;
      esac
      shift 2
      ;;
    *)
      echo "ERROR: unknown validation option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$deep_validation" != "0" && "$deep_validation" != "1" ]]; then
  echo "ERROR: DEEP_VALIDATION must be 0 or 1" >&2
  exit 1
fi

if [[ "$acceptance_discovery" == "1" && ( -z "$target_paper_id" || -z "$acceptance_evidence_file" || -z "$acceptance_paper_id" ) ]]; then
  echo "ERROR: acceptance discovery requires a scoped paper id and evidence file" >&2
  exit 1
fi

if [[ -n "$acceptance_evidence_file" && ( -z "$target_paper_id" || "$target_paper_id" != "$acceptance_paper_id" ) ]]; then
  echo "ERROR: acceptance evidence requires matching scoped and preflight paper ids" >&2
  exit 1
fi

if [[ -n "$acceptance_target_status" && "$acceptance_target_status" != "translated" ]]; then
  echo "ERROR: acceptance target status must be translated" >&2
  exit 1
fi

if [[ -n "$acceptance_target_status" && -z "$acceptance_recorded_waivers" ]]; then
  echo "ERROR: translated acceptance preflight requires recorded waiver evidence" >&2
  exit 1
fi

failures=0
warnings=0
record_count=0
translation_count=0
translation_file_count=0
reviewed_risks=0

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

record_observed_waiver() {
  local evidence_path=$1
  local category=$2
  local candidates=$3
  local candidate
  while IFS= read -r candidate; do
    candidate=$(printf '%s' "$candidate" | tr '\t\r' '  ')
    [[ -n "${candidate//[[:space:]]/}" ]] || continue
    printf '%s\t%s\n' "$category" "$candidate" >> "$evidence_path"
  done <<< "$candidates"
}

for command_name in rg pdfinfo pdftotext perl sed awk find sort mktemp; do
  command -v "$command_name" >/dev/null 2>&1 || fail "required command is unavailable: $command_name"
done

if ! "$PYTHON" --version >/dev/null 2>&1; then
  fail "configured Python is unavailable: $PYTHON"
fi

(( failures == 0 )) || exit 1
metadata_args=(validate)
[[ -n "$target_paper_id" ]] && metadata_args+=(--paper-id "$target_paper_id")
"$PYTHON" scripts/papers.py "${metadata_args[@]}" || exit 1
source_args=(--root "$ROOT")
[[ -n "$target_paper_id" ]] && source_args+=(--paper-id "$target_paper_id")
"$PYTHON" scripts/validate_source_pdf.py "${source_args[@]}" || exit 1
validation_tmp=$(mktemp -d "${TMPDIR:-/tmp}/db-papers-validation.XXXXXX")
manifest="$validation_tmp/manifest"
trap 'rm -rf "$validation_tmp"' EXIT
manifest_args=(validation-manifest)
[[ -n "$target_paper_id" ]] && manifest_args+=(--paper-id "$target_paper_id")
[[ -n "$acceptance_paper_id" ]] && manifest_args+=(--acceptance-paper-id "$acceptance_paper_id")
[[ -n "$acceptance_target_status" ]] && manifest_args+=(--acceptance-target-status "$acceptance_target_status")
[[ -n "$acceptance_recorded_waivers" ]] && manifest_args+=(--acceptance-recorded-waivers "$acceptance_recorded_waivers")
"$PYTHON" scripts/papers.py "${manifest_args[@]}" > "$manifest" || exit 1

{
IFS=$'\x1f' read -r manifest_kind source_name translation_name require_complete_references allow_whole_page_images
[[ "$manifest_kind" == "config" ]] || {
  fail "validation manifest is missing its config row"
  exit 1
}

while IFS=$'\x1f' read -r manifest_kind dir reading_status paper_page_limit acceptance_waivers skip_reason paper_title quality_severity review_grade; do
  [[ "$manifest_kind" == "paper" ]] || {
    fail "validation manifest contains an invalid row"
    continue
  }
  paper_id=${dir##*/}
  record_count=$((record_count + 1))
  pdf="$dir/$source_name"
  translation="$dir/$translation_name"
  observed_acceptance_evidence="$validation_tmp/observed-${paper_id}.tsv"
  : > "$observed_acceptance_evidence"

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

  visible_translation="$validation_tmp/visible-${paper_id}.md"
  if ! "$PYTHON" scripts/markdown_visibility.py "$translation" "$visible_translation"; then
    fail "$translation reader-visible Markdown preparation failed"
    continue
  fi

  fence_count=$(rg -c '^```' "$visible_translation" 2>/dev/null || true)
  (( fence_count % 2 == 0 )) || fail "$translation has unbalanced fenced code blocks"

  if [[ "$allow_whole_page_images" == "false" ]] && rg -q -i '!\[[^]]*\]\([^)]*(original-)?page[-_ ]?[0-9]|整页截图' "$visible_translation"; then
    quality_issue "$translation contains a whole-page screenshot"
  fi

  if rg -q -i '覆盖索引|图像资源索引|仍需人工确认|未嵌入项|contact[ -]?sheet|crop candidate|rework log|本轮|视觉确认|PDF[[:space:]]*抽取|请结合[^。\n]*source\.pdf[^。\n]*(补齐|还原)|QA[[:space:]]*(记录|说明|残留)' "$visible_translation"; then
    quality_issue "$translation contains review or workflow residue"
  fi

  if rg -q '^#{1,4} .*(还原覆盖|公式覆盖说明|步骤保留|表格转写|图表、公式与代码清单|公式与算法自检)' "$visible_translation"; then
    quality_issue "$translation contains workflow-style headings"
  fi

  if rg -q -i '(^|[^[:alpha:]])(TODO|FIXME|TBD)([^[:alpha:]]|$)|待补译|待返工|仍需补充|人工确认后通过' "$visible_translation"; then
    quality_issue "$translation contains unfinished-work markers"
  fi

  if rg -q '^[[:space:]]*[0-9]+\.[[:space:]]+\[[0-9]+\]' "$visible_translation"; then
    quality_issue "$translation contains double-numbered references"
  fi

  narrative_issues=$("$PYTHON" scripts/validate_narrative_voice.py "$visible_translation")
  narrative_status=$?
  if (( narrative_status == 1 )); then
    quality_issue "$translation contains ambiguous bare-author narration: $narrative_issues"
  elif (( narrative_status != 0 )); then
    fail "$translation narrative-voice validation failed (exit=$narrative_status)"
  fi

  github_math_args=("$visible_translation")
  if [[ "$reading_status" == "draft" ]]; then
    github_math_args=(--reject-math-code-spans "$visible_translation")
  fi
  github_math_issues=$("$PYTHON" scripts/validate_github_math.py "${github_math_args[@]}")
  github_math_status=$?
  if (( github_math_status == 1 )); then
    fail "$translation contains non-portable math syntax: $github_math_issues"
  elif (( github_math_status != 0 )); then
    fail "$translation portable math validation failed (exit=$github_math_status)"
  fi

  h1=$(awk '/^# /{print; exit}' "$visible_translation")
  [[ "$h1" == "# ${paper_title}（中文译文）" ]] || quality_issue "$translation H1 must exactly match paper.yaml title plus （中文译文）"
  rg -q '^## 译者说明$' "$visible_translation" || quality_issue "$translation is missing the standard translator-note heading"
  rg -q '^本文依据同目录的 `source\.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。$' "$visible_translation" || quality_issue "$translation is missing the standard translator-note sentence"

  duplicate_images=$(rg -o '!\[[^]]*\]\([^)]*\)' "$visible_translation" 2>/dev/null | sed -E 's/^.*\(([^)]+)\)$/\1/' | sort | uniq -d)
  [[ -z "$duplicate_images" ]] || quality_issue "$translation contains duplicate image references: $duplicate_images"

  broken_images=$(TRANSLATION_BASE="$dir" perl -MFile::Spec -ne '
    while (/!\[[^\]]*\]\((<[^>]+>|[^)[:space:]]+)/g) {
      $path = $1;
      $path =~ s/^<|>$//g;
      next if $path =~ m{^(https?:|data:)};
      $full = File::Spec->rel2abs($path, $ENV{TRANSLATION_BASE});
      print "$path\n" unless -e $full;
    }
  ' "$visible_translation")
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
    listing_issues=$("$PYTHON" scripts/validate_listings.py "$source_text" "$visible_translation")
    listing_status=$?
    if (( listing_status != 0 )); then
      if (( listing_status == 1 )); then
        quality_issue "$translation has deterministic source-listing errors: $listing_issues"
      elif (( listing_status == 3 )); then
        record_observed_waiver "$observed_acceptance_evidence" "listings" "$listing_issues"
        if [[ "$reading_status" == "draft" ]]; then
          warn "$translation has Listing review candidates: $listing_issues"
        fi
      else
        fail "$translation listing validation failed (exit=$listing_status)"
      fi
    fi

    source_chars=$(tr -d '[:space:]' < "$source_text" | wc -m | tr -d ' ')
    translated_chars=$(sed '/^!\[/d;/^---$/d;/^[a-z_]*:/d' "$visible_translation" | tr -d '[:space:]' | wc -m | tr -d ' ')
    if awk -v s="$source_chars" -v t="$translated_chars" 'BEGIN { exit !(s > 0 && t / s < 0.25) }'; then
      quality_issue "$translation has suspiciously low source/translation coverage ($translated_chars/$source_chars)"
    fi

    abridgement_stderr="$validation_tmp/abridgement-${paper_id}.stderr"
    abridgement_args=(abridgement "$pdf" "$visible_translation")
    [[ "$review_grade" == "true" ]] || abridgement_args+=(--legacy-accepted-reference-boundary)
    abridgement_candidate=$("$PYTHON" scripts/pdf_metrics.py "${abridgement_args[@]}" 2>"$abridgement_stderr")
    abridgement_status=$?
    if (( abridgement_status != 0 )); then
      abridgement_error=$(tr '\n\r\t' '   ' < "$abridgement_stderr")
      fail "$translation abridgement metric failed (exit=$abridgement_status): $abridgement_error"
    elif [[ -s "$abridgement_stderr" ]]; then
      abridgement_error=$(tr '\n\r\t' '   ' < "$abridgement_stderr")
      fail "$translation abridgement metric emitted unexpected stderr: $abridgement_error"
    elif [[ -n "$abridgement_candidate" ]]; then
      record_observed_waiver "$observed_acceptance_evidence" "abridgement" "$abridgement_candidate"
      if [[ "$reading_status" == "draft" ]]; then
        warn "$translation has $abridgement_candidate"
      fi
    fi

    source_table_numbers=$(perl -ne 'while (/(?:^|\f|\s{2,})Table\s+(\d+)\s*[:.]/ig) { print "$1\n" }' "$source_text" | sort -nu)
    while IFS= read -r table_number; do
      [[ -z "$table_number" ]] && continue
      rg -q "(表|Table)[[:space:]]*${table_number}([^0-9]|$)" "$visible_translation" || quality_issue "$translation does not identify source Table $table_number"
    done <<< "$source_table_numbers"

    resource_args=("$dir" "$source_text")
    [[ "$require_complete_references" == "true" ]] && resource_args+=(--require-complete-references)
    if [[ "$review_grade" == "true" ]]; then
      resource_args+=(--require-inline-citations)
    else
      resource_args+=(--legacy-accepted-resource-structure)
    fi
    [[ "$allow_whole_page_images" == "true" ]] && resource_args+=(--allow-whole-page-images)
    resource_issues=$("$PYTHON" scripts/validate_resources.py "${resource_args[@]}")
    resource_status=$?
    if (( resource_status == 1 )); then
      quality_issue "$translation has deterministic resource/reference errors: $resource_issues"
    elif (( resource_status == 3 )); then
      record_observed_waiver "$observed_acceptance_evidence" "resources" "$resource_issues"
      if [[ "$reading_status" == "draft" ]]; then
        warn "$translation has resource review candidates: $resource_issues"
      fi
    elif (( resource_status != 0 )); then
      fail "$translation resource validation failed (exit=$resource_status): $resource_issues"
    fi
  fi
  if [[ "$reading_status" == "translated" ]]; then
    waiver_mismatches=$("$PYTHON" scripts/acceptance_evidence.py compare --recorded "$acceptance_waivers" --observed "$observed_acceptance_evidence" 2>&1)
    waiver_match_status=$?
    if (( waiver_match_status == 0 )); then
      while IFS= read -r waiver_match; do
        [[ "$waiver_match" == reviewed:* ]] || continue
        reviewed_risks=$((reviewed_risks + 1))
        echo "REVIEWED-RISK: $translation ${waiver_match#reviewed:}"
      done <<< "$waiver_mismatches"
    elif (( waiver_match_status == 1 )); then
      while IFS= read -r waiver_mismatch; do
        [[ -n "$waiver_mismatch" ]] || continue
        if [[ "$waiver_mismatch" == reviewed:* ]]; then
          reviewed_risks=$((reviewed_risks + 1))
          echo "REVIEWED-RISK: $translation ${waiver_mismatch#reviewed:}"
          continue
        fi
        fail "$translation acceptance waiver evidence mismatch: $waiver_mismatch"
      done <<< "$waiver_mismatches"
    else
      fail "$translation acceptance waiver evidence validation failed: $waiver_mismatches"
    fi
  elif [[ "$reading_status" == "draft" && -s "$observed_acceptance_evidence" ]]; then
    evidence_summary=$("$PYTHON" scripts/acceptance_evidence.py summarize --observed "$observed_acceptance_evidence" 2>&1)
    evidence_summary_status=$?
    if (( evidence_summary_status == 0 )); then
      printf '%s\n' "$evidence_summary"
    else
      fail "$translation acceptance evidence summary failed: $evidence_summary"
    fi
  fi
  if [[ -n "$acceptance_evidence_file" ]]; then
    cat "$observed_acceptance_evidence" >> "$acceptance_evidence_file" || fail "cannot write acceptance evidence: $acceptance_evidence_file"
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
  echo "Deep translation validation passed: $record_count records and $translation_count translated papers ($warnings warning(s), $reviewed_risks reviewed-risk category group(s))."
else
  echo "Fast translation validation passed: $record_count records and $translation_count translated papers ($warnings warning(s))."
fi
