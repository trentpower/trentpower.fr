#!/usr/bin/env bash
# shellcheck disable=SC2034 # T_REPLY is set here, consumed by the sourcing build.sh
# term.sh -- render primitives for the trentpower.fr publication ceremony.
#
# Sourced by tools/build/build.sh. Pure presentation: nothing here affects the
# build, validation, signing or publication logic. Mirrors the JS reference
# `term-core.js` (markers, panels, spinner, prompts) so the CLI build reads like
# the graphical reference, while degrading to a clean, colourless, box-free
# transcript when piped / NO_COLOR / not a TTY.
#
# Render mode is decided ONCE by build.sh and exported before sourcing:
#   T_RENDER   rich | plain      (plain == no colour, no box-drawing, no spinner)
#   T_ASCII    0 | 1             (markers use [ ] [*] [ok] [!] [x] - instead of glyphs)
#   T_VERBOSE  0 | 1             (echo each underlying command, dimmed, prefixed `$ `)
#
# Every interactive prompt is non-blocking off a TTY: it resolves to a declared
# default and prints that choice statically, so a piped build never hangs.
#
# All colour is a single oxblood accent plus status greens/ambers/reds
# (BUILD_RENDER_BRIEF.md §1.1). Box inner width is 52 columns (§1.4).

: "${T_RENDER:=plain}"
: "${T_ASCII:=0}"
: "${T_VERBOSE:=0}"

T_BW=52    # panel inner content width
T_REPLY="" # last prompt result (menu key / typed text / yes|no)

t_is_tty() { [ -t 1 ]; }

# ── colour ──────────────────────────────────────────────────────────────────
# t_c ROLE -> emit an SGR foreground escape (truecolor where COLORTERM allows,
# else a 256-colour fallback), or nothing in plain mode. t_z resets; t_b bolds.
t_c() {
  [ "$T_RENDER" = rich ] || return 0
  case "$1" in
  ox) set -- 194 87 60 173 ;;
  ox_deep) set -- 140 58 46 95 ;;
  paper) set -- 232 226 216 230 ;;
  ink) set -- 220 214 203 252 ;;
  ink_dim) set -- 152 143 131 245 ;;
  ink_faint) set -- 93 86 77 240 ;;
  ok) set -- 131 165 102 107 ;;
  warn) set -- 203 155 77 179 ;;
  fail) set -- 204 86 64 167 ;;
  *) return 0 ;;
  esac
  case "${COLORTERM:-}" in
  truecolor | 24bit) printf '\033[38;2;%d;%d;%dm' "$1" "$2" "$3" ;;
  *) printf '\033[38;5;%dm' "$4" ;;
  esac
}
t_z() { if [ "$T_RENDER" = rich ]; then printf '\033[0m'; fi; }
t_b() { if [ "$T_RENDER" = rich ]; then printf '\033[1m'; fi; }

# t_seg ROLE TEXT -> coloured run, no newline. t_say ROLE TEXT -> + newline.
t_seg() { printf '%s%s%s' "$(t_c "$1")" "$2" "$(t_z)"; }
t_say() { printf '%s\n' "$(t_seg "$1" "$2")"; }

# t_rule CHAR N -> CHAR repeated N times (works for box-drawing glyphs).
t_rule() {
  local s='' i=0
  while [ "$i" -lt "$2" ]; do
    s="$s$1"
    i=$((i + 1))
  done
  printf '%s' "$s"
}

# ── status markers (meaning survives without colour) ────────────────────────
t_mark() {
  local ascii=0
  { [ "$T_RENDER" = plain ] || [ "$T_ASCII" = 1 ]; } && ascii=1
  case "$1" in
  pending) if [ "$ascii" = 1 ]; then printf '[ ]'; else t_seg ink_faint '○'; fi ;;
  active) if [ "$ascii" = 1 ]; then printf '[*]'; else t_seg ox '●'; fi ;;
  pass) if [ "$ascii" = 1 ]; then printf '[ok]'; else t_seg ok '✓'; fi ;;
  warn) if [ "$ascii" = 1 ]; then printf '[!]'; else t_seg warn '!'; fi ;;
  fail) if [ "$ascii" = 1 ]; then printf '[x]'; else t_seg fail '×'; fi ;;
  skip) if [ "$ascii" = 1 ]; then printf '-'; else t_seg ink_dim '·'; fi ;;
  esac
}

# ── stage header + lifecycle flow line ──────────────────────────────────────
# t_stage NN TITLE [purpose]
t_stage() {
  printf '\n%s%s%s%s  %s%s%s%s\n' \
    "$(t_c ox)" "$(t_b)" "$1" "$(t_z)" \
    "$(t_c paper)" "$(t_b)" "$2" "$(t_z)"
  [ -n "${3:-}" ] && t_say ink_faint "$3"
  return 0
}

# t_flow a b c ...  ->  a → b → c   (trailing node emphasised)
t_flow() {
  local out='' i=1 n=$# x arrow=' → '
  { [ "$T_RENDER" = plain ] || [ "$T_ASCII" = 1 ]; } && arrow=' -> '
  for x in "$@"; do
    if [ "$i" -eq "$n" ]; then out="$out$(t_seg paper "$x")"; else out="$out$(t_seg ink_dim "$x")"; fi
    [ "$i" -lt "$n" ] && out="$out$(t_seg ox "$arrow")"
    i=$((i + 1))
  done
  printf '   %s\n' "$out"
}

# ── spinner ─────────────────────────────────────────────────────────────────
# A single in-flight activity. Rich+TTY: a braille spinner redrawn on \r,
# replaced by the resolved marker. Plain / non-TTY: nothing until resolved.
_T_SPIN_PID=''
_T_SPIN_MSG=''
t_spin_start() {
  _T_SPIN_MSG="$1"
  { [ "$T_RENDER" = rich ] && t_is_tty; } || return 0
  local frames ox rst
  # shellcheck disable=SC1003 # the trailing backslash is a literal spinner frame
  if [ "$T_ASCII" = 1 ]; then frames='| / - \'; else frames='⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏'; fi
  ox="$(t_c ox)"
  rst="$(t_z)"
  (
    read -ra F <<<"$frames"
    local i=0
    while :; do
      printf '\r   %s%s%s %s' "$ox" "${F[i]}" "$rst" "$_T_SPIN_MSG"
      i=$(((i + 1) % ${#F[@]}))
      sleep 0.09
    done
  ) &
  _T_SPIN_PID=$!
}
# t_spin_stop ROLE MSG [TAIL]
t_spin_stop() {
  local role="$1" msg="$2" tail="${3:-}"
  if [ -n "$_T_SPIN_PID" ]; then
    kill "$_T_SPIN_PID" 2>/dev/null || true
    wait "$_T_SPIN_PID" 2>/dev/null || true
    _T_SPIN_PID=''
  fi
  local line
  line="   $(t_mark "$role") $msg"
  [ -n "$tail" ] && line="$line   $(t_seg ink_dim "$tail")"
  if { [ "$T_RENDER" = rich ] && t_is_tty; }; then
    printf '\r\033[K%s\n' "$line"
  else
    printf '%s\n' "$line"
  fi
}

# t_verbose_cmd CMD... -> echo the command dimmed, prefixed `$ ` (verbose only)
t_verbose_cmd() {
  [ "$T_VERBOSE" = 1 ] || return 0
  printf '      %s\n' "$(t_seg ink_faint "\$ $*")"
}

# t_run MSG -- CMD...  (or  t_run MSG CMD...) -> spinner around CMD.
# Output is hidden on success, shown on failure; returns CMD's exit code.
t_run() {
  local msg="$1"
  shift
  [ "${1:-}" = '--' ] && shift
  t_verbose_cmd "$@"
  t_spin_start "$msg"
  local out rc
  out="$("$@" 2>&1)"
  rc=$?
  if [ "$rc" -eq 0 ]; then
    t_spin_stop pass "$msg"
  else
    t_spin_stop fail "$msg"
    [ -n "$out" ] && printf '%s\n' "$out" >&2
  fi
  return "$rc"
}

# ── panels (buffered so keys align; box-drawing rich, indented text plain) ───
_T_PTITLE=''
_T_PK=()
_T_PV=()
_T_PTONE=()
_T_PSUB=()
t_panel_open() {
  _T_PTITLE="$1"
  _T_PK=()
  _T_PV=()
  _T_PTONE=()
  _T_PSUB=()
}
t_panel_row() {
  _T_PK+=("$1")
  _T_PV+=("$2")
  _T_PTONE+=("${3:-ink}")
  _T_PSUB+=("")
}
t_panel_sub() {
  _T_PK+=("")
  _T_PV+=("")
  _T_PTONE+=("")
  _T_PSUB+=("$1")
}
t_panel_close() {
  local n=${#_T_PK[@]} i kw=0
  for ((i = 0; i < n; i++)); do
    if [ -z "${_T_PSUB[i]}" ] && [ "${#_T_PK[i]}" -gt "$kw" ]; then kw=${#_T_PK[i]}; fi
  done

  if [ "$T_RENDER" = plain ]; then
    printf '%s\n' "$_T_PTITLE"
    for ((i = 0; i < n; i++)); do
      if [ -n "${_T_PSUB[i]}" ]; then
        printf '  -- %s\n' "${_T_PSUB[i]}"
      else
        printf '  %-*s   %s\n' "$kw" "${_T_PK[i]}" "${_T_PV[i]}"
      fi
    done
    return 0
  fi

  local fc dashes
  fc="$(t_c ink_faint)"
  dashes=$((T_BW - ${#_T_PTITLE} - 3))
  [ "$dashes" -lt 0 ] && dashes=0
  printf '%s┌─ %s%s %s%s┐%s\n' \
    "$fc" "$(t_z)$(t_c ox)$_T_PTITLE$fc" "" "$(t_rule '─' "$dashes")" "" "$(t_z)"

  for ((i = 0; i < n; i++)); do
    if [ -n "${_T_PSUB[i]}" ]; then
      local lbl=" ${_T_PSUB[i]} " sd
      sd=$((T_BW - ${#lbl} - 2))
      [ "$sd" -lt 0 ] && sd=0
      printf '%s├──%s%s┤%s\n' \
        "$fc" "$(t_z)$fc$lbl$fc" "$(t_rule '─' "$sd")" "$(t_z)"
    else
      local k="${_T_PK[i]}" v="${_T_PV[i]}" tone="${_T_PTONE[i]}" pad vis
      vis=$((2 + kw + 3 + ${#v}))
      pad=$((T_BW - vis))
      [ "$pad" -lt 0 ] && pad=0
      local kpad
      printf -v kpad '%-*s' "$kw" "$k"
      printf '%s│%s  %s%s%s   %s%s%s%s%s│%s\n' \
        "$fc" "$(t_z)" \
        "$(t_c ink_dim)" "$kpad" "$(t_z)" \
        "$(t_c "$tone")" "$v" "$(t_z)" \
        "$(t_rule ' ' "$pad")" "$fc" "$(t_z)"
    fi
  done

  printf '%s└%s┘%s\n' "$fc" "$(t_rule '─' "$T_BW")" "$(t_z)"
  return 0
}

# ── bordered banner (single-line rows, used for INTENT / CHECK MODE) ─────────
t_banner() {
  local l
  if [ "$T_RENDER" = plain ]; then
    for l in "$@"; do printf '%s\n' "$l"; done
    return 0
  fi
  local fc W=$T_BW
  fc="$(t_c ink_faint)"
  printf '%s┌%s┐%s\n' "$fc" "$(t_rule '─' "$W")" "$(t_z)"
  for l in "$@"; do
    local pad=$((W - 2 - ${#l}))
    [ "$pad" -lt 0 ] && pad=0
    printf '%s│%s %s%s %s│%s\n' \
      "$fc" "$(t_z)" "$(t_c paper)$l$(t_z)" "$(t_rule ' ' "$pad")" "$fc" "$(t_z)"
  done
  printf '%s└%s┘%s\n' "$fc" "$(t_rule '─' "$W")" "$(t_z)"
  return 0
}

# ── interactive prompts (never block off a TTY) ─────────────────────────────
# t_menu KEY=LABEL ...   -> prints options, reads a key into T_REPLY.
t_menu() {
  local o k l
  for o in "$@"; do
    k="${o%%=*}"
    l="${o#*=}"
    printf '   %s %s\n' "$(t_seg ox "[$k]")" "$(t_seg ink "$l")"
  done
  if ! t_is_tty; then
    T_REPLY="${1%%=*}"
    return 0
  fi
  local ans=''
  printf '   %s ' "$(t_seg ink_dim '›')"
  read -r ans </dev/tty || ans=''
  T_REPLY="$ans"
  return 0
}

# t_ask_text PROMPT DEFAULT [HINT] -> reads a line (default if empty) into T_REPLY.
t_ask_text() {
  local prompt="$1" def="${2:-}" hint="${3:-}"
  if ! t_is_tty; then
    T_REPLY="$def"
    printf '   %s %s\n' "$(t_seg ink_dim "$prompt ›")" "$(t_seg paper "$def")"
    return 0
  fi
  [ -n "$hint" ] && t_say ink_faint "   $hint"
  local ans=''
  printf '   %s ' "$(t_seg ink_dim "$prompt ›")"
  read -r -e -i "$def" ans </dev/tty || ans="$def"
  ans="${ans:-$def}"
  T_REPLY="$ans"
  return 0
}

# t_confirm_yn PROMPT [yes|no] -> T_REPLY=yes|no; exit 0 for yes, 1 for no.
t_confirm_yn() {
  local prompt="$1" def="${2:-no}"
  if ! t_is_tty; then
    if [ "$def" = yes ]; then
      T_REPLY=yes
      return 0
    fi
    T_REPLY=no
    return 1
  fi
  local hint='[y/N]'
  [ "$def" = yes ] && hint='[Y/n]'
  local ans=''
  printf '   %s %s ' "$(t_seg paper "$prompt")" "$(t_seg ink_dim "$hint")"
  read -r ans </dev/tty || ans=''
  ans="${ans:-$def}"
  case "$ans" in
  [Yy]*)
    T_REPLY=yes
    return 0
    ;;
  [Nn]*)
    T_REPLY=no
    return 1
    ;;
  *)
    if [ "$def" = yes ]; then
      T_REPLY=yes
      return 0
    fi
    T_REPLY=no
    return 1
    ;;
  esac
}

# t_confirm_word PROMPT WORD [HINT] -> T_REPLY=typed; exit 0 only on exact match.
# Off a TTY this NEVER auto-confirms (returns 1) -- deploy must be deliberate.
t_confirm_word() {
  local prompt="$1" word="$2" hint="${3:-}"
  if ! t_is_tty; then
    T_REPLY=''
    return 1
  fi
  [ -n "$hint" ] && t_say ink_faint "   $hint"
  local ans=''
  printf '   %s ' "$(t_seg ink_dim "$prompt ›")"
  read -r ans </dev/tty || ans=''
  T_REPLY="$ans"
  [ "$ans" = "$word" ]
}
