set -euo pipefail
BASECSS_FILE="$(dirname "$0")/_page_base.css"
basecss(){ cat "$BASECSS_FILE"; }

write_page(){
  local out="$1"; shift
  mkdir -p "$(dirname "$out")"
  {
    cat <<'EOF'
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <link rel="stylesheet" href="/_page_style.css"/>
  <style>
EOF
    basecss
    cat <<'EOF'
  </style>
EOF
    # title/desc/canonical/meta injected by caller via stdin block later
  } > "$out"
}
