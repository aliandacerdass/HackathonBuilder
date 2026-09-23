#!/usr/bin/env bash
# Push öncesi sızıntı kontrolü. git pre-push hook'u stdin'den şu satırları verir:
#   <local ref> <local sha> <remote ref> <remote sha>
# Herhangi bir bulgu varsa exit 1 → push iptal.
set -uo pipefail

ZERO=0000000000000000000000000000000000000000
fail=0

red()   { printf '\033[31m%s\033[0m\n' "$1"; }
green() { printf '\033[32m%s\033[0m\n' "$1"; }

# 1) Ignore edilmesi gerekip takip edilen dosya var mı?
tracked_ignored=$(git ls-files -ci --exclude-standard)
if [ -n "$tracked_ignored" ]; then
  red "✗ .gitignore'da olup git'te takip edilen dosyalar:"
  echo "$tracked_ignored"
  fail=1
fi

# Bu script kalıpları içerdiği için taramadan hariç
EXCLUDE=':!scripts/pre-push-check.sh'

PATTERNS=(
  'sk-[A-Za-z0-9_-]{20,}'                  # OpenAI / Anthropic key
  'AIza[0-9A-Za-z_-]{35}'                   # Google API key
  'gh[pousr]_[A-Za-z0-9]{36}'               # GitHub token
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'      # private key
  '/Users/[^/[:space:]]+/'                  # ev dizini (kişisel yol)
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'  # e-posta
)
ALLOW='noreply@|example\.com'

while read -r local_ref local_sha remote_ref remote_sha; do
  [ "$local_sha" = "$ZERO" ] && continue   # branch silme
  if [ "$remote_sha" = "$ZERO" ]; then
    range="$local_sha --not --remotes"
    log_opts="$local_sha --not --remotes"
  else
    range="$remote_sha..$local_sha"
    log_opts="$remote_sha..$local_sha"
  fi

  # 2) gitleaks: gönderilecek commit'lerde secret taraması
  if command -v gitleaks >/dev/null; then
    if ! gitleaks git --no-banner --redact --log-opts="$log_opts" .; then
      red "✗ gitleaks secret buldu."
      fail=1
    fi
  else
    red "✗ gitleaks kurulu değil (brew install gitleaks)."
    fail=1
  fi

  # 3) Ek kalıplar: sadece eklenen satırlar
  # shellcheck disable=SC2086
  added=$(git log -p --format= $range -- . "$EXCLUDE" | grep '^+' | grep -v '^+++')
  for p in "${PATTERNS[@]}"; do
    hits=$(printf '%s\n' "$added" | grep -Eo -- "$p" | grep -Ev "$ALLOW")
    if [ -n "$hits" ]; then
      red "✗ Şüpheli içerik (kalıp: $p):"
      printf '%s\n' "$hits" | sort -u | sed 's/^/    /'
      fail=1
    fi
  done
done

if [ "$fail" -ne 0 ]; then
  red "PUSH İPTAL. Bulguları temizle, sonra tekrar dene. (--no-verify YASAK — RULES.md)"
  exit 1
fi
green "✓ Sızıntı kontrolü temiz."
