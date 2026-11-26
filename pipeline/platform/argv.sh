# The unified argument parser — the bash adapter.
#
# A sourced library implementing the one contract whose
# home is pipeline/platform/argv.py, over the same
# declarations, held to the same clauses by the shared
# fixture corpus (argv_fixtures.json): both value forms
# are one flag; unknown flags, unknown verbs, and
# surplus positionals refuse with usage at exit 2; a
# value flag missing its value, or handed a flag-shaped
# token in the space form, is a usage error; flag order
# never changes semantics; safety flags fail closed; a
# repeated scalar flag is last-wins; abbreviations are
# never accepted; usage is generated from the
# declaration. The bootstrap class sources this file
# in-process — it takes no Python dependency.
#
# A tool declares its surface once:
#
#   source "$(dirname "$0")/argv.sh"     # or its path
#   argv_tool mytool "one-line summary"
#   argv_global_flag caller value required
#   argv_global_flag verbose bool
#   argv_verb acquire "Acquire a session."
#   argv_flag shape value required
#   argv_positional session
#   argv_end_verb
#   argv_parse "$@" || exit 2
#
# Flag kinds are "value" and "bool"; flag attributes
# are the bare words required / repeatable / safety and
# the pairs default=V, short=C, choices=a,b,c.
# Positional attributes are required / variadic (last
# positional only). argv_mode_group NAME f1,f2[,required]
# declares a mutually exclusive mode group in the
# current scope.
#
# Parse results: ARGV_VERB (empty for a verb-less
# tool), ARGV_FLAGS (associative: every declared flag
# of the active scope, booleans as true/false, value
# flags as their value or empty when absent with no
# default, repeatables newline-joined), ARGV_PRESENT
# (associative set of flags actually given),
# ARGV_POSITIONALS (associative by positional name;
# a variadic value is newline-joined), ARGV_HELP=1
# when help was requested (usage already printed).

declare -A _ARGV_KIND=() _ARGV_REQ=() _ARGV_REP=() _ARGV_SAFE=()
declare -A _ARGV_DEF=() _ARGV_HASDEF=() _ARGV_SHORT=() _ARGV_CHOICES=()
declare -A _ARGV_POSSPECS=() _ARGV_GROUPS=() _ARGV_VERB_SUMMARY=()
declare -a _ARGV_VERBS=()
ARGV_TOOL="" ARGV_SUMMARY="" _ARGV_SCOPE="global"
declare -A ARGV_FLAGS=() ARGV_PRESENT=() ARGV_POSITIONALS=()
ARGV_VERB="" ARGV_HELP=0

argv_tool() {
  ARGV_TOOL="$1"; ARGV_SUMMARY="${2:-}"; _ARGV_SCOPE="global"
}

_argv_decl_flag() {
  local scope="$1" name="$2" kind="$3"; shift 3
  local key="$scope|$name"
  _ARGV_KIND["$key"]="$kind"
  _ARGV_REQ["$key"]=0 _ARGV_REP["$key"]=0 _ARGV_SAFE["$key"]=0
  _ARGV_HASDEF["$key"]=0 _ARGV_DEF["$key"]="" _ARGV_SHORT["$key"]=""
  _ARGV_CHOICES["$key"]=""
  local attr
  for attr in "$@"; do
    case "$attr" in
      required) _ARGV_REQ["$key"]=1 ;;
      repeatable) _ARGV_REP["$key"]=1 ;;
      safety) _ARGV_SAFE["$key"]=1 ;;
      default=*) _ARGV_HASDEF["$key"]=1; _ARGV_DEF["$key"]="${attr#default=}" ;;
      short=*) _ARGV_SHORT["$key"]="${attr#short=}" ;;
      choices=*) _ARGV_CHOICES["$key"]="${attr#choices=}" ;;
      *) echo "argv: bad flag attribute: $attr" >&2; return 2 ;;
    esac
  done
}

argv_global_flag() { _argv_decl_flag "global" "$@"; }
argv_flag() { _argv_decl_flag "$_ARGV_SCOPE" "$@"; }

argv_verb() {
  _ARGV_VERBS+=("$1")
  _ARGV_VERB_SUMMARY["$1"]="${2:-}"
  _ARGV_SCOPE="$1"
}

argv_end_verb() { _ARGV_SCOPE="global"; }

_argv_decl_positional() {
  local scope="$1" name="$2"; shift 2
  local req=0 var=0 attr
  for attr in "$@"; do
    case "$attr" in
      required) req=1 ;;
      variadic) var=1 ;;
      *) echo "argv: bad positional attribute: $attr" >&2; return 2 ;;
    esac
  done
  _ARGV_POSSPECS["$scope"]="${_ARGV_POSSPECS[$scope]:-} $name:$req:$var"
}

argv_global_positional() { _argv_decl_positional "global" "$@"; }
argv_positional() { _argv_decl_positional "$_ARGV_SCOPE" "$@"; }

_argv_decl_group() {
  local scope="$1" name="$2" flags="$3" req="${4:-}"
  local reqbit=0
  [ "$req" = "required" ] && reqbit=1
  _ARGV_GROUPS["$scope"]="${_ARGV_GROUPS[$scope]:-} $name:$flags:$reqbit"
}

argv_global_mode_group() { _argv_decl_group "global" "$@"; }
argv_mode_group() { _argv_decl_group "$_ARGV_SCOPE" "$@"; }

_argv_flag_kind() {  # scope name -> kind or empty
  local key="$1|$2"
  if [ -n "${_ARGV_KIND[$key]:-}" ]; then printf '%s' "${_ARGV_KIND[$key]}"
  elif [ "$1" != "global" ] && [ -n "${_ARGV_KIND[global|$2]:-}" ]; then
    printf '%s' "${_ARGV_KIND[global|$2]}"
  fi
}

_argv_union_kind() {  # name -> kind across all scopes
  local name="$1" scope key
  for scope in "global" "${_ARGV_VERBS[@]}"; do
    key="$scope|$name"
    if [ -n "${_ARGV_KIND[$key]:-}" ]; then
      printf '%s' "${_ARGV_KIND[$key]}"; return
    fi
  done
}

_argv_short_name() {  # char -> flag name in scope (or global)
  local scope="$1" ch="$2" key name
  for key in "${!_ARGV_SHORT[@]}"; do
    if [ "${_ARGV_SHORT[$key]}" = "$ch" ]; then
      name="${key#*|}"
      case "$key" in "$scope|"*|"global|"*) printf '%s' "$name"; return ;;
      esac
    fi
  done
}

_argv_flag_shaped() {  # token -> 0 if flag-shaped
  local token="$1"
  case "$token" in --|--*|-h) return 0 ;; esac
  if [ "${#token}" -ge 2 ] && [ "${token:0:1}" = "-" ]; then
    local name
    name="$(_argv_union_short "${token:1:1}")"
    [ -n "$name" ] && return 0
  fi
  return 1
}

_argv_union_short() {  # char -> some flag name declaring it
  local ch="$1" key
  for key in "${!_ARGV_SHORT[@]}"; do
    if [ "${_ARGV_SHORT[$key]}" = "$ch" ]; then printf '%s' "${key#*|}"; return; fi
  done
}

_argv_find_verb() {  # head tokens -> verb candidate or empty
  local -a toks=("$@")
  local i=0 n=${#toks[@]} token name kind
  while [ "$i" -lt "$n" ]; do
    token="${toks[$i]}"
    case "$token" in
      --*)
        name="${token:2}"; name="${name%%=*}"
        kind="$(_argv_union_kind "$name")"
        if [ "$kind" = "value" ] && [ "$token" != *"="* ]; then i=$((i + 2));
        else i=$((i + 1)); fi ;;
      -*)
        if [ "${#token}" -ge 2 ]; then
          name="$(_argv_union_short "${token:1:1}")"
          if [ -n "$name" ]; then
            kind="$(_argv_union_kind "$name")"
            if [ "$kind" = "value" ] && [ "$token" != *"="* ] && [ "${#token}" -eq 2 ];
            then i=$((i + 2)); else i=$((i + 1)); fi
          else i=$((i + 1)); fi
        else i=$((i + 1)); fi ;;
      *) printf '%s' "$token"; return ;;
    esac
  done
}

argv_usage() {
  local verb="${1:-}"
  local scope="global" name key kind line
  if [ -n "$verb" ]; then scope="$verb"; fi
  {
    if [ -n "$verb" ]; then
      printf 'usage: %s %s [flags]\n' "$ARGV_TOOL" "$verb"
      [ -n "${_ARGV_VERB_SUMMARY[$verb]:-}" ] && printf '%s\n' "${_ARGV_VERB_SUMMARY[$verb]}"
    else
      printf 'usage: %s' "$ARGV_TOOL"
      if [ "${#_ARGV_VERBS[@]}" -gt 0 ]; then
        printf ' <'
        local IFS='|'; printf '%s' "${_ARGV_VERBS[*]}"; IFS=' '
        printf '> [flags]'
      fi
      printf '\n'
      [ -n "$ARGV_SUMMARY" ] && printf '%s\n' "$ARGV_SUMMARY"
      if [ "${#_ARGV_VERBS[@]}" -gt 0 ]; then
        printf 'verbs:\n'
        local v
        for v in "${_ARGV_VERBS[@]}"; do
          printf '  %s  %s\n' "$v" "${_ARGV_VERB_SUMMARY[$v]:-}"
        done
      fi
    fi
    printf 'flags:\n'
    for key in "${!_ARGV_KIND[@]}"; do
      case "$key" in "$scope|"*|"global|"*) ;;
        *) continue ;;
      esac
      name="${key#*|}"; kind="${_ARGV_KIND[$key]}"
      line="  --$name"
      [ -n "${_ARGV_SHORT[$key]:-}" ] && line="$line|-${_ARGV_SHORT[$key]}"
      [ "$kind" = "value" ] && line="$line VALUE"
      [ "${_ARGV_REQ[$key]}" = "1" ] && line="$line (required)"
      [ "${_ARGV_REP[$key]}" = "1" ] && line="$line (repeatable)"
      [ "${_ARGV_SAFE[$key]}" = "1" ] && line="$line (safety: fails closed)"
      printf '%s\n' "$line"
    done
    local specs="${_ARGV_POSSPECS[$scope]:-}" spec pname preq pvar
    if [ -n "$specs" ]; then
      printf 'positionals:\n'
      for spec in $specs; do
        pname="${spec%%:*}"; rest="${spec#*:}"
        preq="${rest%%:*}"; pvar="${rest##*:}"
        line="  $pname"
        [ "$preq" = "1" ] && line="$line (required)"
        [ "$pvar" = "1" ] && line="$line (variadic)"
        printf '%s\n' "$line"
      done
    fi
    local groups="${_ARGV_GROUPS[global]:-}"
    if [ "$scope" != "global" ]; then
      groups="$groups ${_ARGV_GROUPS[$scope]:-}"
    fi
    local group gname gflags greq
    for group in $groups; do
      gname="${group%%:*}"; rest="${group#*:}"
      gflags="${rest%%:*}"; greq="${rest##*:}"
      line="mode group $gname: one of"
      local IFS=','
      for f in $gflags; do line="$line --$f"; done
      IFS=' '
      [ "$greq" = "1" ] && line="$line (required)"
      printf '%s\n' "$line"
    done
  }
}

_argv_fail() {
  printf '%s: %s\n' "$ARGV_TOOL" "$1" >&2
  argv_usage "${ARGV_VERB:-}" >&2
  return 2
}

_argv_store() {  # scope name value
  local scope="$1" name="$2" value="$3"
  local key="$scope|$name" gkey="global|$name"
  local rep="${_ARGV_REP[$key]:-${_ARGV_REP[$gkey]:-0}}"
  local choices="${_ARGV_CHOICES[$key]:-${_ARGV_CHOICES[$gkey]:-}}"
  if [ -n "$choices" ]; then
    case ",$choices," in
      *,"$value",*) ;;
      *) _argv_fail "flag --$name takes one of $choices; got $value"; return 2 ;;
    esac
  fi
  ARGV_PRESENT["$name"]=1
  if [ "$rep" = "1" ]; then
    if [ -n "${ARGV_FLAGS[$name]:-}" ]; then
      ARGV_FLAGS["$name"]="${ARGV_FLAGS[$name]}"$'\n'"$value"
    else
      ARGV_FLAGS["$name"]="$value"
    fi
  else
    ARGV_FLAGS["$name"]="$value"
  fi
}

argv_canon() {
  # The canonical dump of the last parse — the corpus
  # driver's surface: one line per fact, in the shared
  # form every implementation's corpus runner compares
  # (verb, then flag:<name>=<value>, then
  # pos:<name>=<value>; booleans as true/false, an
  # absent value flag as null, lists comma-joined).
  if [ "${ARGV_HELP:-0}" = "1" ]; then echo "help"; return 0; fi
  local scope="${ARGV_VERB:-global}"
  if [ -n "${ARGV_VERB:-}" ]; then echo "verb=$ARGV_VERB"; else echo "verb=-"; fi
  local -A printed=()
  local key name kind v
  for key in "${!_ARGV_KIND[@]}"; do
    case "$key" in "$scope|"*|"global|"*) ;;
      *) continue ;;
    esac
    name="${key#*|}"
    [ -n "${printed[$name]:-}" ] && continue
    printed["$name"]=1
    kind="${_ARGV_KIND[$key]}"
    v="${ARGV_FLAGS[$name]:-}"
    if [ -n "${ARGV_PRESENT[$name]:-}" ]; then
      v="${v//$'\n'/,}"
    elif [ "${_ARGV_REP[$key]}" = "1" ]; then
      v=""
    elif [ "$kind" = "value" ] && [ "${_ARGV_HASDEF[$key]}" != "1" ]; then
      v="null"
    fi
    echo "flag:$name=$v"
  done
  local specs spec pname pvar
  specs="${_ARGV_POSSPECS[$scope]:-}"
  for spec in $specs; do
    pname="${spec%%:*}"; pvar="${spec##*:}"
    v="${ARGV_POSITIONALS[$pname]:-}"
    if [ -z "$v" ] && [ "$pvar" != "1" ]; then
      v="null"
    else
      v="${v//$'\n'/,}"
    fi
    echo "pos:$pname=$v"
  done
}

argv_parse() {
  ARGV_FLAGS=() ARGV_PRESENT=() ARGV_POSITIONALS=()
  ARGV_VERB="" ARGV_HELP=0
  local -a head=() tail=() bare=()
  local seen_sep=0 token
  for token in "$@"; do
    if [ "$seen_sep" = "0" ] && [ "$token" = "--" ]; then
      seen_sep=1; continue
    fi
    if [ "$seen_sep" = "0" ]; then head+=("$token"); else tail+=("$token"); fi
  done
  for token in "${head[@]}"; do
    if [ "$token" = "--help" ] || [ "$token" = "-h" ]; then
      ARGV_HELP=1
      argv_usage "$(_argv_find_verb "${head[@]}")"
      return 0
    fi
  done
  local scope="global"
  if [ "${#_ARGV_VERBS[@]}" -gt 0 ]; then
    ARGV_VERB="$(_argv_find_verb "${head[@]}")"
    if [ -z "$ARGV_VERB" ]; then
      _argv_fail "a verb is required"; return 2
    fi
    local known=0 v
    for v in "${_ARGV_VERBS[@]}"; do [ "$v" = "$ARGV_VERB" ] && known=1; done
    if [ "$known" = "0" ]; then _argv_fail "unknown verb $ARGV_VERB"; return 2; fi
    scope="$ARGV_VERB"
  fi
  local verb_seen=0
  [ -z "$ARGV_VERB" ] && verb_seen=1
  local i=0 n=${#head[@]} name kind spec_key value rest
  while [ "$i" -lt "$n" ]; do
    token="${head[$i]}"
    if [ "$verb_seen" = "0" ] && [ "$token" = "$ARGV_VERB" ]; then
      verb_seen=1; i=$((i + 1)); continue
    fi
    case "$token" in
      --*)
        local body="${token:2}"
        if [[ "$body" == *"="* ]]; then
          name="${body%%=*}"; value="${body#*=}"; local has_eq=1
        else
          name="$body"; value=""; local has_eq=0
        fi
        kind="$(_argv_flag_kind "$scope" "$name")"
        if [ -z "$kind" ]; then _argv_fail "unknown flag --$name"; return 2; fi
        if [ "$kind" = "value" ]; then
          if [ "$has_eq" = "0" ]; then
            if [ $((i + 1)) -ge "$n" ] || _argv_flag_shaped "${head[$((i + 1))]}";
            then _argv_fail "flag --$name needs a value"; return 2; fi
            i=$((i + 1)); value="${head[$i]}"
          fi
          _argv_store "$scope" "$name" "$value" || return 2
        else
          if [ "$has_eq" = "1" ]; then
            _argv_fail "flag --$name takes no value"; return 2
          fi
          _argv_store "$scope" "$name" "true" || return 2
        fi ;;
      -*)
        if [ "$token" != "-" ] && [ "${#token}" -ge 2 ]; then
          name="$(_argv_short_name "$scope" "${token:1:1}")"
          if [ -z "$name" ]; then _argv_fail "unknown flag $token"; return 2; fi
          kind="$(_argv_flag_kind "$scope" "$name")"
          rest="${token:2}"
          if [ "$kind" = "value" ]; then
            if [[ "$rest" == "="* ]]; then value="${rest#=}"
            elif [ -n "$rest" ]; then value="$rest"
            else
              if [ $((i + 1)) -ge "$n" ] || _argv_flag_shaped "${head[$((i + 1))]}";
              then _argv_fail "flag --$name needs a value"; return 2; fi
              i=$((i + 1)); value="${head[$i]}"
            fi
            _argv_store "$scope" "$name" "$value" || return 2
          else
            if [ -n "$rest" ]; then _argv_fail "unknown flag $token"; return 2; fi
            _argv_store "$scope" "$name" "true" || return 2
          fi
        else
          bare+=("$token")
        fi ;;
      *) bare+=("$token") ;;
    esac
    i=$((i + 1))
  done
  bare+=("${tail[@]}")
  # positionals
  local specs="${_ARGV_POSSPECS[$scope]:-}"
  if [ "$scope" = "global" ]; then specs="${_ARGV_POSSPECS[global]:-}"; fi
  local -a speclist=($specs)
  local idx=0 spec pname preq pvar bi
  for spec in "${speclist[@]}"; do
    pname="${spec%%:*}"; rest="${spec#*:}"
    preq="${rest%%:*}"; pvar="${rest##*:}"
    if [ "$pvar" = "1" ]; then
      local joined=""
      for ((bi = idx; bi < ${#bare[@]}; bi++)); do
        if [ -n "$joined" ]; then joined="$joined"$'\n'"${bare[$bi]}";
        else joined="${bare[$bi]}"; fi
      done
      ARGV_POSITIONALS["$pname"]="$joined"
      idx=${#bare[@]}
    elif [ "$idx" -lt "${#bare[@]}" ]; then
      ARGV_POSITIONALS["$pname"]="${bare[$idx]}"; idx=$((idx + 1))
    elif [ "$preq" = "1" ]; then
      _argv_fail "positional $pname is required"; return 2
    else
      ARGV_POSITIONALS["$pname"]=""
    fi
  done
  if [ "$idx" -lt "${#bare[@]}" ]; then
    _argv_fail "surplus positional ${bare[$idx]}"; return 2
  fi
  # defaults + required flags
  local key s name2
  for key in "${!_ARGV_KIND[@]}"; do
    case "$key" in "$scope|"*|"global|"*) ;;
      *) continue ;;
    esac
    name2="${key#*|}"
    if [ -z "${ARGV_PRESENT[$name2]:-}" ]; then
      if [ "${_ARGV_REQ[$key]}" = "1" ]; then
        _argv_fail "flag --$name2 is required"; return 2
      fi
      if [ "${_ARGV_KIND[$key]}" = "bool" ]; then
        ARGV_FLAGS["$name2"]="false"
      elif [ "${_ARGV_HASDEF[$key]}" = "1" ]; then
        ARGV_FLAGS["$name2"]="${_ARGV_DEF[$key]}"
      else
        ARGV_FLAGS["$name2"]=""
      fi
    fi
  done
  # mode groups
  local groups="${_ARGV_GROUPS[global]:-}"
  if [ "$scope" != "global" ]; then
    groups="$groups ${_ARGV_GROUPS[$scope]:-}"
  fi
  local group gname gflags greq f count
  for group in $groups; do
    gname="${group%%:*}"; rest="${group#*:}"
    gflags="${rest%%:*}"; greq="${rest##*:}"
    count=0
    local IFS=','
    for f in $gflags; do
      [ -n "${ARGV_PRESENT[$f]:-}" ] && count=$((count + 1))
    done
    IFS=' '
    if [ "$count" -gt 1 ]; then
      _argv_fail "mode group $gname takes one of $gflags"; return 2
    fi
    if [ "$greq" = "1" ] && [ "$count" = "0" ]; then
      _argv_fail "mode group $gname requires one of $gflags"; return 2
    fi
  done
  return 0
}
