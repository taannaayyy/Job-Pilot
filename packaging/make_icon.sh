#!/bin/sh
# Renders icon.svg to icon.icns (macOS) and icon.ico (Windows) with headless Chrome, iconutil and
# ImageMagick. Only needed when the icon changes.
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
tmp=$(mktemp -d)
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 \
  --window-size=1024,1024 --screenshot="$tmp/icon_1024.png" "file://$PWD/icon.svg" 2>/dev/null
mkdir "$tmp/icon.iconset"
for size in 16 32 128 256 512; do
  sips -z $size $size "$tmp/icon_1024.png" --out "$tmp/icon.iconset/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z $double $double "$tmp/icon_1024.png" --out "$tmp/icon.iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$tmp/icon.iconset" -o icon.icns
cp "$tmp/icon_1024.png" icon.png
# The Windows icon (several sizes in one file), with ImageMagick.
magick icon.png -define icon:auto-resize=256,128,64,48,32,24,16 icon.ico
rm -rf "$tmp"
echo "wrote packaging/icon.icns and packaging/icon.ico"
