#!/usr/bin/env bash

# Compare tab-separated acceptance waivers with the candidates observed by the
# deep validator. Output is stable and machine-readable for the caller.

has_waiver() {
  local waiver_list=$1
  local expected=$2
  [[ $'\t'"$waiver_list"$'\t' == *$'\t'"$expected"$'\t'* ]]
}

waiver_values() {
  local waiver_list=$1
  [[ -n "$waiver_list" ]] || return 0
  printf '%s\n' "$waiver_list" | tr '\t' '\n'
}

compare_acceptance_waivers() {
  local recorded=$1
  local observed=$2
  local waiver
  local status=0

  while IFS= read -r waiver; do
    [[ -n "$waiver" ]] || continue
    if ! has_waiver "$recorded" "$waiver"; then
      printf 'missing:%s\n' "$waiver"
      status=1
    fi
  done < <(waiver_values "$observed")

  while IFS= read -r waiver; do
    [[ -n "$waiver" ]] || continue
    if ! has_waiver "$observed" "$waiver"; then
      printf 'unused:%s\n' "$waiver"
      status=1
    fi
  done < <(waiver_values "$recorded")

  return "$status"
}
