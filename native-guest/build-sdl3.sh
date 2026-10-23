#!/usr/bin/env bash
# Build an official, unchanged SDL3 shared runtime in a local prefix.
set -euo pipefail
task_root="$(cd "$(dirname "$0")" && pwd)"
task_source="$task_root/.sdl3-source"
task_build="$task_root/.sdl3-build"
task_prefix="$task_root/.sdl3"
task_commit=7f3ae3d57459e59943a4ecfefc8f6277ec6bf540
command -v git >/dev/null
command -v cmake >/dev/null
if [[ ! -d "$task_source/.git" ]]; then
  [[ ! -e "$task_source" ]] || { echo 'SDL source destination already exists; inspect it first.' >&2; exit 1; }
  git init "$task_source"
  git -C "$task_source" remote add origin https://github.com/libsdl-org/SDL.git
fi
git -C "$task_source" fetch --depth 1 origin "$task_commit"
[[ "$(git -C "$task_source" rev-parse FETCH_HEAD)" == "$task_commit" ]]
git -C "$task_source" checkout --detach "$task_commit"
[[ -z "$(git -C "$task_source" status --porcelain)" ]] || { echo 'SDL source has local changes; inspect them before building.' >&2; exit 1; }
cmake -S "$task_source" -B "$task_build" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$task_prefix" -DCMAKE_INSTALL_LIBDIR=lib \
  -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TESTS=OFF -DSDL_TEST_LIBRARY=OFF
cmake --build "$task_build" --parallel 4
cmake --install "$task_build"
echo 'SDL3 built locally. Preserve the installed SDL3 license when redistributing it.'
