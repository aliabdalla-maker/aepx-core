#!/bin/sh
# Regenerates every app icon and store graphic from the SVG sources in this folder.
# Needs: rsvg-convert (librsvg) and ImageMagick `convert`. Run from anywhere: sh brand/make_assets.sh
set -eu
B=$(cd "$(dirname "$0")" && pwd)
IDE=$(dirname "$B")
png() { rsvg-convert -w "$2" -h "$2" "$B/$1.svg" -o "$3"; }
opaque() { convert "$1" -background '#0b1020' -alpha remove -alpha off "$1"; }  # stores reject alpha

# Android launcher icons: adaptive (foreground + monochrome + colour background) and legacy PNGs
RES="$IDE/android-companion/app/src/main/res"
for d in mdpi:1 hdpi:1.5 xhdpi:2 xxhdpi:3 xxxhdpi:4; do
  name=${d%%:*}; f=${d##*:}
  mkdir -p "$RES/mipmap-$name"
  png logo-foreground $(awk "BEGIN{print int(108*$f)}") "$RES/mipmap-$name/ic_launcher_foreground.png"
  png logo-monochrome $(awk "BEGIN{print int(108*$f)}") "$RES/mipmap-$name/ic_launcher_monochrome.png"
  png logo $(awk "BEGIN{print int(48*$f)}") "$RES/mipmap-$name/ic_launcher.png"
  png logo $(awk "BEGIN{print int(48*$f)}") "$RES/mipmap-$name/ic_launcher_round.png"
done

# Google Play store listing graphics (32-bit PNG icon 512x512; feature graphic 1024x500 without alpha)
PLAY="$IDE/distribution/play-listing/graphics"; mkdir -p "$PLAY"
png logo-square 512 "$PLAY/icon-512.png"
rsvg-convert -w 1024 -h 500 "$B/feature-graphic.svg" -o "$PLAY/feature-graphic-1024x500.png"; opaque "$PLAY/feature-graphic-1024x500.png"

# iOS: one 1024x1024 opaque App Store icon per app (Xcode derives the other sizes)
for app in Companion IDEWrapper; do
  SET="$IDE/ios/$app/Assets.xcassets/AppIcon.appiconset"; mkdir -p "$SET"
  png logo-square 1024 "$SET/AppIcon-1024.png"; opaque "$SET/AppIcon-1024.png"
  printf '%s\n' '{"images":[{"filename":"AppIcon-1024.png","idiom":"universal","platform":"ios","size":"1024x1024"}],"info":{"author":"xcode","version":1}}' > "$SET/Contents.json"
  printf '%s\n' '{"info":{"author":"xcode","version":1}}' > "$IDE/ios/$app/Assets.xcassets/Contents.json"
done

# Desktop (electron-builder derives .ico/.icns/Linux sizes from build/icon.png)
mkdir -p "$IDE/desktop/build"; png logo-desktop 1024 "$IDE/desktop/build/icon.png"

# Web IDE + website
cp "$B/logo.svg" "$IDE/web/app/icon.svg"
mkdir -p "$IDE/web/public/icons"
png logo 192 "$IDE/web/public/icons/icon-192.png"; png logo 512 "$IDE/web/public/icons/icon-512.png"
png logo-foreground 512 "$IDE/web/public/icons/maskable-512.png"
convert "$IDE/web/public/icons/maskable-512.png" -background '#0b1020' -alpha remove -alpha off "$IDE/web/public/icons/maskable-512.png"
png logo 180 "$IDE/web/app/apple-icon.png"
SITE="$IDE/distribution/website/static/aepx"; mkdir -p "$SITE"
cp "$B/logo.svg" "$SITE/logo.svg"; cp "$B/wordmark.svg" "$SITE/wordmark.svg"
png logo 512 "$SITE/logo-512.png"; png logo 180 "$SITE/apple-touch-icon.png"
rsvg-convert -w 1024 -h 500 "$B/feature-graphic.svg" -o "$SITE/og-image.png"
for s in 16 32 48; do png logo $s "/tmp/aepx-fav-$s.png"; done
convert /tmp/aepx-fav-16.png /tmp/aepx-fav-32.png /tmp/aepx-fav-48.png "$SITE/favicon.ico"
echo "brand assets regenerated"
