#!/usr/bin/env bash
set -euo pipefail
# Ephemeral runner only. One explicitly approved KVM ACL; no licence acceptance/cache/uploads.
export JAVA_HOME="${JAVA_HOME_21_X64:?Runner Java 21 required}"
export PATH="$JAVA_HOME/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
export GRADLE_USER_HOME="$RUNNER_TEMP/foodsave-gradle"
export ANDROID_USER_HOME="$RUNNER_TEMP/foodsave-android"
export ANDROID_AVD_HOME="$ANDROID_USER_HOME/avd"
mkdir -p "$ANDROID_AVD_HOME"
if [[ ! -r /dev/kvm || ! -w /dev/kvm ]]; then
  command -v setfacl >/dev/null || { printf 'BLOCKED: setfacl absent; no package installation authorized.\n'; exit 2; }
  sudo setfacl -m "u:$(id -un):rw" /dev/kvm
  [[ -r /dev/kvm && -w /dev/kvm ]]
fi
# stdin is closed: an unaccepted licence must fail, never auto-accept it.
sdkmanager 'emulator' 'platforms;android-36' 'build-tools;35.0.0' 'system-images;android-35;google_apis;x86_64' < /dev/null
emulator -accel-check
npm ci --ignore-scripts --no-audit --no-fund
npm run build
npx --no-install cap sync android
(cd android && bash ./gradlew --no-daemon --no-build-cache :app:assembleDebug)
apk=android/app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/build-tools/35.0.0/apksigner" verify --verbose "$apk"
"$ANDROID_HOME/build-tools/35.0.0/aapt" dump badging "$apk" | sed -n '1,5p'
sha256sum "$apk"
stat -c 'APK bytes: %s' "$apk"
printf 'no\n' | avdmanager create avd --name foodsave-ci --package 'system-images;android-35;google_apis;x86_64' --device pixel_2
emulator -avd foodsave-ci -port 5554 -no-window -no-audio -no-boot-anim -no-snapshot -gpu software -accel on -memory 2048 > "$RUNNER_TEMP/foodsave-emulator.log" 2>&1 &
emulator_pid=$!
trap 'adb -s emulator-5554 emu kill >/dev/null 2>&1 || true; kill "$emulator_pid" 2>/dev/null || true' EXIT
for attempt in {1..90}; do
  if [[ "$(adb -s emulator-5554 shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == 1 ]]; then break; fi
  if ! kill -0 "$emulator_pid" 2>/dev/null; then tail -60 "$RUNNER_TEMP/foodsave-emulator.log"; exit 3; fi
  sleep 2
done
[[ "$(adb -s emulator-5554 shell getprop sys.boot_completed | tr -d '\r')" == 1 ]]
adb -s emulator-5554 shell service check package | grep -q found
adb -s emulator-5554 shell input keyevent 82
adb -s emulator-5554 install -r "$apk"
adb -s emulator-5554 shell am start -W -n tw.foodsave.demo/.MainActivity
node scripts/android-ci.cjs
