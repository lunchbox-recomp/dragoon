# Launcher developer notes

The launcher is the macOS app that builds the game on the player's Mac. These notes cover what a developer needs to build and check it. The tools are described in [tools/README.md](../tools/README.md).

## Third-party pieces

`third_party.txt` pins CMake and Ninja by version, URL and SHA-256. `tools/fetch_third_party.py` is the only thing that downloads them. SDL's pin lives in gcn-recomp's `CMakeLists.txt` and is read from there. Downloads go to `launcher/.third_party/`, which git ignores.

```
launcher/tools/fetch_third_party.py --dest launcher/.third_party
```

| Item | Version | Download | Size | Where the pin's hash came from |
|---|---|---|---|---|
| CMake | 4.4.4 | `cmake-4.4.4-macos-universal.tar.gz` | 89.5 MB | Kitware's `cmake-4.4.4-SHA-256.txt`, which the release page's digest agrees with |
| Ninja | 1.13.2 | `ninja-mac.zip` | 314 KB | The digest GitHub shows for the asset, since Ninja publishes no hash file |
| SDL | 3.4.18 | `SDL3-3.4.18.tar.gz` | 15.7 MB | The `sdl3` `FetchContent_Declare` in gcn-recomp |

All three downloads matched their pins on the first fetch.

## Audit of the fetched binaries

Run on this Mac on 2026-10-23, with the fetched copies and nothing else. Neither binary was run beyond `--version`.

| | `cmake` (`CMake.app/Contents/bin/cmake`) | `ninja` |
|---|---|---|
| `--version` | `cmake version 4.4.4` | `1.13.2` |
| `lipo -info` | universal, `x86_64 arm64` | universal, `x86_64 arm64` |
| `codesign -dv` | Developer ID Application: Kitware Inc. (W38PE5Y733), hardened runtime, signed 2026-10-02 | ad hoc, no team ID |
| `codesign --verify --strict` | passes | not run |
| Size | 26.6 MB (both slices) | 828 KB (both slices) |

`otool -L` shows only system libraries, and the same list for both slices of each binary.

| Binary | Libraries |
|---|---|
| `cmake` | In `/usr/lib`: `libcurl.4`, `libiconv.2`, `libcharset.1`, `libz.1`, `libc++.1` and `libSystem.B`. In `/System/Library/Frameworks`: CoreFoundation and CoreServices |
| `ninja` | `/usr/lib/libc++.1.dylib` and `/usr/lib/libSystem.B.dylib` |

Both ship universal, so `make_app.py` thins each to arm64 with `lipo`. That drops Kitware's signature from `cmake`, and the app is signed again ad hoc for dev builds. A release signs it with our Developer ID.

CMake's tarball holds the whole `CMake.app`, with the Qt frameworks of `cmake-gui`. The launcher uses only `Contents/bin/cmake` and `Contents/share/cmake-4.4` (24 MB).

## Licenses

`make_app.py` copies each license into `Contents/Resources/licenses/`.

| Piece | License | Where `make_app.py` finds it |
|---|---|---|
| CMake | BSD 3-clause | `Contents/doc/cmake/LICENSE.rst` in its tarball, with `CONTRIBUTORS.rst` and the `cm*` directories that hold the notices of the libraries built into it (libuv, libarchive, zstd, lzma, librhash, cppdap and KWSys). The rest of that directory is the manual and stays out |
| Ninja | Apache 2.0 | `launcher/ninja-COPYING.txt` |
| SDL | zlib | `LICENSE.txt` in its tarball |
| Dragoon, gcn-recomp | each repo's `LICENSE` | the source snapshot |

`ninja-mac.zip` holds only the `ninja` binary and no license text. `ninja-COPYING.txt` is the `COPYING` of Ninja's `v1.13.2` tag. It was copied from Homebrew's Ninja 1.13.2 and then compared with the tag by git blob ID (`131cb1da46d238a296d448fd79acf37160817cf6`), which matches.

## The dev app

`launcher/Info.plist` sets the bundle ID `io.github.lunchbox-recomp.dragoon`. It's a placeholder until a final one is chosen, and it should stay fixed once players have the app, since macOS keys settings and permissions to it. The minimum macOS is 14.0 and the app has no icon.

`tools/make_app.py` assembles `Dragoon.app` from the launcher binary SwiftPM built, so run `swift build -c release --package-path launcher` first. Its tests use fake inputs for every piece and run without Swift.
