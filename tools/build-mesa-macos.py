#!/usr/bin/env python3
"""Isolated macOS host-tool preparation for pinned Switch Mesa.

Never install into /opt/devkitpro. Existing downloads stay under --root.
"""
from pathlib import Path
import subprocess
import os


def build_environment(root, stage):
    """Discard inherited cross flags; explicitly pick native tools and target Rust."""
    env = os.environ.copy()
    llvm = root / "toolchains/mesa-llvm/llvm@21" / LLVM_VERSION
    rust = root / "toolchains/mesa-rust/rustup/toolchains/1.93.1-aarch64-apple-darwin/bin"
    spirv = root / "toolchains/mesa-spirv-tools/spirv-tools" / SPIRV_VERSION
    env.update({
        "PATH": ":".join(map(str, [root / "toolchains/mesa-python/bin", llvm / "bin", rust,
                                  root / "toolchains/mesa-rust/cargo/bin",
                                  root / "toolchains/mesa-cbindgen/cbindgen/0.29.4/bin",
                                  "/opt/homebrew/opt/bison/bin", "/opt/homebrew/bin",
                                  "/usr/bin", "/bin", "/opt/devkitpro/devkitA64/bin",
                                  "/opt/devkitpro/tools/bin"])),
        "CARGO_HOME": str(root / "toolchains/mesa-rust/cargo"),
        "RUSTUP_HOME": str(root / "toolchains/mesa-rust/rustup"),
        "MESA_SWITCH_RUST_TARGET": "aarch64-unknown-linux-gnu",
        "MESA_SWITCH_RUSTC": str(rust / "rustc"),
        "MESA_SWITCH_BINDGEN": str(root / "toolchains/mesa-rust/cargo/bin/bindgen"),
        "LIBCLANG_PATH": str(llvm / "lib"),
        "DEVKITPRO": "/opt/devkitpro",
        "CC": "/usr/bin/clang", "CXX": "/usr/bin/clang++", "OBJC": "/usr/bin/clang",
        "CFLAGS": "", "CXXFLAGS": "", "CPPFLAGS": "", "LDFLAGS": "",
        "PKG_CONFIG_PATH": "" if stage == "cross" else
                           f"{root}/mesa-vulkan/host/lib/pkgconfig:{spirv}/lib/pkgconfig",
    })
    for key in ("PKG_CONFIG_LIBDIR", "PKG_CONFIG_SYSROOT_DIR", "RUSTFLAGS",
                "BINDGEN_EXTRA_CLANG_ARGS", "RUSTC", "AR", "CC_FOR_BUILD", "CXX_FOR_BUILD"):
        env.pop(key, None)
    if stage == "cross":
        env["PATH"] = str(root / "mesa-vulkan/tools") + ":" + env["PATH"]
    return env


def build_commands(root, jobs):
    """All outputs isolated; two jobs maximum for the 8 GiB build host."""
    if jobs not in (1, 2):
        raise ValueError("Use --jobs 1 or 2")
    out = root / "mesa-vulkan"
    src = str(root / "mesa-switch")
    llvm = root / "toolchains/mesa-llvm/llvm@21" / LLVM_VERSION
    meson = str(root / "toolchains/mesa-python/bin/meson")
    return [
        ("translator-configure", ["cmake", "-G", "Ninja", "-S", str(root / "toolchains/mesa-spirv-translator"),
            "-B", str(out / "spirv-translator-build"), "-DCMAKE_BUILD_TYPE=Release",
            f"-DLLVM_DIR={llvm}/lib/cmake/llvm", f"-DCMAKE_INSTALL_PREFIX={out}/host",
            f"-DLLVM_EXTERNAL_SPIRV_HEADERS_SOURCE_DIR={root}/toolchains/mesa-spirv-headers",
            "-DLLVM_SPIRV_INCLUDE_TESTS=OFF", "-DBUILD_SHARED_LIBS=ON", "-DLLVM_LINK_LLVM_DYLIB=ON",
            "-DCMAKE_C_COMPILER=/usr/bin/clang", "-DCMAKE_CXX_COMPILER=/usr/bin/clang++"]),
        ("translator-build", ["cmake", "--build", str(out / "spirv-translator-build"), "--parallel", str(jobs)]),
        ("translator-install", ["cmake", "--install", str(out / "spirv-translator-build")]),
        ("native-configure", [meson, "setup", str(out / "native"), src, "--buildtype=release",
            "-Dvulkan-drivers=", "-Dgallium-drivers=", "-Dshader-cache=enabled", "-Dplatforms=",
            "-Dglx=disabled", "-Degl=disabled", "-Dopengl=false", "-Dgles1=disabled", "-Dgles2=disabled",
            "-Dtools=[]", "-Dllvm=enabled", "-Dmesa-clc=enabled", "-Dprecomp-compiler=enabled", "-Dinstall-mesa-clc=true"]),
        ("native-build", ["ninja", "-C", str(out / "native"), f"-j{jobs}",
            "src/compiler/clc/mesa_clc", "src/compiler/spirv/vtn_bindgen2"]),
        ("cross-configure", [meson, "setup", str(out / "cross"), src,
            "--cross-file", str(out / "switch-macos.txt"), "--native-file", str(out / "native-macos.txt"),
            "--default-library=static", "--prefix=/opt/devkitpro/portlibs/switch", "--libdir=lib",
            "--buildtype=release", "-Doptimization=2", "-Db_lto=false", "-Db_ndebug=true",
            "-Dvulkan-drivers=nouveau", "-Dgallium-drivers=nouveau", "-Dgallium-rusticl=false",
            "-Dplatforms=switch", "-Degl-native-platform=switch", "-Dglx=disabled", "-Degl=enabled",
            "-Dopengl=true", "-Dgles1=enabled", "-Dgles2=enabled", "-Dvideo-codecs=", "-Dshader-cache=enabled",
            "-Dxmlconfig=enabled", "-Dexpat=enabled", "-Dtools=[]", "-Dllvm=disabled", "-Dshared-glapi=disabled",
            "-Dshared-llvm=disabled", "-Dmesa-clc=system", "-Dprecomp-compiler=system", "-Dcpp_rtti=false",
            "-Dbuild-tests=false", f"-Dnvk-build-id={MESA_REVISION}"]),
        ("cross-build", ["ninja", "-C", str(out / "cross"), f"-j{jobs}"]),
        ("install", [meson, "install", "-C", str(out / "cross"), "--no-rebuild", "--destdir", str(out / "install")]),
    ]


def relocate_bottle(prefix, root):
    """Relocate only extracted Mach-O binaries and pkg-config metadata."""
    for path in sorted(prefix.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix == ".pc":
            text = path.read_text()
            changed = relocated_path(text, root)
            if changed != text:
                path.write_text(changed)
            continue
        with path.open("rb") as stream:
            magic = stream.read(4)
        if magic not in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
            continue
        command = ["install_name_tool"]
        ids = subprocess.check_output(["otool", "-D", str(path)], text=True).splitlines()[1:]
        if ids and "@@HOMEBREW" in ids[0]:
            command += ["-id", relocated_path(ids[0], root)]
        deps = subprocess.check_output(["otool", "-L", str(path)], text=True).splitlines()[1:]
        for line in deps:
            dep = line.strip().split(" (compatibility", 1)[0]
            if dep in ids or "@@HOMEBREW" not in dep:
                continue
            replacement = relocated_path(dep, root)
            if not Path(replacement).exists():
                raise FileNotFoundError(replacement)
            command += ["-change", dep, replacement]
        if len(command) > 1:
            subprocess.run(command + [str(path)], check=True)
            subprocess.run(["codesign", "--force", "--sign", "-", str(path)], check=True)

MESA_REVISION = "b297e230ef88c6c88df2561becf864f979f494a6"
LLVM_VERSION = "21.1.8"
SPIRV_VERSION = "1.4.357.0"


def relocated_path(value, root):
    """Resolve bottle placeholders without linking another LLVM version."""
    mappings = {
        "@@HOMEBREW_PREFIX@@/opt/llvm@21": root / "toolchains/mesa-llvm/llvm@21" / LLVM_VERSION,
        "@@HOMEBREW_CELLAR@@/llvm@21": root / "toolchains/mesa-llvm/llvm@21",
        "@@HOMEBREW_PREFIX@@/opt/spirv-tools": root / "toolchains/mesa-spirv-tools/spirv-tools" / SPIRV_VERSION,
        "@@HOMEBREW_CELLAR@@/spirv-tools": root / "toolchains/mesa-spirv-tools/spirv-tools",
        "@@HOMEBREW_PREFIX@@/opt/zstd": Path("/opt/homebrew/opt/zstd"),
    }
    for old, new in mappings.items():
        value = value.replace(old, str(new))
    if "@@HOMEBREW" in value:
        raise ValueError(f"Unresolved bottle path: {value}")
    return value


def cross_configuration(template, root):
    """Separate Darwin generators/proc-macros from Horizon target objects."""
    out = root / "mesa-vulkan"
    rust = root / "toolchains/mesa-rust/rustup/toolchains/1.93.1-aarch64-apple-darwin/bin/rustc"
    for old, new in (
        ("/usr/local/libexec/rustc", str(out / "tools/rustc")),
        ("/usr/local/libexec/bindgen", str(out / "tools/bindgen")),
        ("'-L/opt/devkitpro/portlibs/switch/lib'",
         f"'-L{out}/compat/lib', '-L/opt/devkitpro/portlibs/switch/lib'"),
    ):
        if old not in template:
            raise ValueError(f"Missing cross-file anchor: {old}")
        template = template.replace(old, new)
    template += "\n[properties]\nneeds_exe_wrapper = true\n"
    native = f"""[binaries]
c = '/usr/bin/clang'
cpp = '/usr/bin/clang++'
objc = '/usr/bin/clang'
rust = '{rust}'
mesa_clc = '{out}/native/src/compiler/clc/mesa_clc'
vtn_bindgen2 = '{out}/native/src/compiler/spirv/vtn_bindgen2'
cbindgen = '{root}/toolchains/mesa-cbindgen/cbindgen/0.29.4/bin/cbindgen'
"""
    return template, native


def verify_archive(path):
    """Check every real member is ELF64 little-endian AArch64, not Darwin/COFF."""
    import hashlib
    size = path.stat().st_size
    members = 0
    with path.open("rb") as stream:
        if stream.read(8) != b"!<arch>\n":
            raise ValueError(f"Not a regular archive (possibly thin): {path}")
        while stream.tell() < size:
            header = stream.read(60)
            if len(header) != 60 or header[58:60] != b"`\n":
                raise ValueError(f"Malformed archive: {path}")
            name = header[:16].strip()
            length = int(header[48:58])
            start = stream.tell()
            if start + length > size:
                raise ValueError(f"Truncated archive: {path}")
            if name not in (b"/", b"//", b"/SYM64/"):
                data = stream.read(min(length, 20))
                if len(data) != 20 or data[:6] != b"\x7fELF\x02\x01" or data[18:20] != b"\xb7\x00":
                    raise ValueError(f"Non-AArch64 ELF member {name!r} in {path}")
                members += 1
            stream.seek(start + length + length % 2)
    if not members:
        raise ValueError(f"Empty target archive: {path}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": size, "members": members, "machine": "AArch64", "sha256": digest}


def verify_install(root):
    """Link real Switch ELF/NRO and record exact archive hashes after validation."""
    import hashlib
    import json
    out = root / "mesa-vulkan"
    sdk = out / "install/opt/devkitpro/portlibs/switch"
    names = ("EGL", "GL", "glapi", "vulkan", "mesa_util_c11", "blake3",
             "mesa_util", "mesa_util_simd", "xmlconfig")
    archives = [sdk / "lib" / f"lib{name}.a" for name in names]
    for archive in archives:
        if not archive.is_file():
            raise FileNotFoundError(archive)
        subprocess.run(["/opt/devkitpro/devkitA64/bin/aarch64-none-elf-ranlib", str(archive)], check=True)
    verified = [verify_archive(p) for p in archives]
    headers = {}
    for tree in ("vulkan", "vk_video"):
        for source in sorted((root / "mesa-switch/include" / tree).rglob("*.h")):
            relative = source.relative_to(root / "mesa-switch/include")
            installed = sdk / "include" / relative
            if installed.read_bytes() != source.read_bytes():
                raise ValueError(f"Pinned header mismatch: {relative}")
            headers[str(relative)] = hashlib.sha256(installed.read_bytes()).hexdigest()
    source = out / "link-smoke.c"
    source.write_text('#include <vulkan/vulkan.h>\n#include <EGL/egl.h>\n#include <GL/gl.h>\n'
                      'int main(void) { unsigned version=0; vkEnumerateInstanceVersion(&version); '
                      'eglGetDisplay(EGL_DEFAULT_DISPLAY); glGetString(GL_VERSION); return version == 0; }\n')
    command = ["/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc", str(source),
               "-D__SWITCH__", f"-I{sdk}/include", "-I/opt/devkitpro/libnx/include",
               "-march=armv8-a+crc+crypto", "-mtune=cortex-a57", "-mtp=soft", "-fPIC",
               "-ffunction-sections", "-fdata-sections", "-specs=/opt/devkitpro/libnx/switch.specs",
               "-L/opt/devkitpro/libnx/lib", "-L/opt/devkitpro/portlibs/switch/lib",
               "-Wl,--gc-sections", "-Wl,--start-group", *map(str, archives),
               "-lexpat", "-lzstd", "-lz", "-Wl,--end-group", "-lstdc++", "-lnx", "-lm",
               "-o", str(out / "link-smoke.elf")]
    with (out / "link-smoke.log").open("w") as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(["/opt/devkitpro/tools/bin/elf2nro", str(out / "link-smoke.elf"),
                        str(out / "link-smoke.nro")], check=True, stdout=log, stderr=subprocess.STDOUT)
    manifest = {"mesa_revision": MESA_REVISION, "mesa_version": "26.2.2",
                "target": "aarch64-horizon", "llvm_version": LLVM_VERSION,
                "rust_version": "1.93.1", "bindgen_version": "0.72.1", "cbindgen_version": "0.29.4",
                "libraries": verified, "headers_sha256": headers, "link_smoke_command": command,
                "switch_hardware_tested": False}
    for name in ("link-smoke.elf", "link-smoke.nro"):
        manifest[name] = {"bytes": (out / name).stat().st_size,
                          "sha256": hashlib.sha256((out / name).read_bytes()).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def write_changed(path, text):
    """Preserve setup mtimes so a resumed build need not recompile unchanged inputs."""
    if not path.is_file() or path.read_text() != text:
        path.write_text(text)


def main():
    import argparse
    import json
    import shlex
    import shutil
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / ".cache/pes13-nx-macos")
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=2)
    parser.add_argument("--stage", choices=("prepare", "native", "cross", "install", "verify", "all"), default="all")
    parser.add_argument("--plan", action="store_true", help="Print commands; no writes or prerequisite checks")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    commands = build_commands(root, args.jobs)
    if args.plan:
        for name, command in commands:
            print(name + ": " + shlex.join(command))
        return 0
    src, out = root / "mesa-switch", root / "mesa-vulkan"
    revision = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    if revision != MESA_REVISION:
        raise RuntimeError(f"Mesa pin mismatch: {revision}; expected {MESA_REVISION}")
    subprocess.run(["git", "-C", str(src), "diff", "--exit-code", "HEAD", "--"], check=True)
    env_native = build_environment(root, "native")
    env_cross = build_environment(root, "cross")
    if args.stage in ("prepare", "all"):
        out.mkdir(parents=True, exist_ok=True)
        llvm = root / "toolchains/mesa-llvm/llvm@21" / LLVM_VERSION
        spirv = root / "toolchains/mesa-spirv-tools/spirv-tools" / SPIRV_VERSION
        required = [llvm / "bin/llvm-config", spirv / "lib/libSPIRV-Tools.dylib",
                    Path(env_cross["MESA_SWITCH_RUSTC"]), Path(env_cross["MESA_SWITCH_BINDGEN"]),
                    root / "toolchains/mesa-cbindgen/cbindgen/0.29.4/bin/cbindgen",
                    root / "toolchains/mesa-python/bin/meson"]
        missing = [str(p) for p in required if not p.is_file()]
        if missing:
            raise RuntimeError("Missing prepared tools (see docs/MESA-MACOS.md): " + ", ".join(missing))
        relocate_bottle(llvm, root)
        relocate_bottle(spirv, root)
        cross, native = cross_configuration((src / "switch_cross_file.txt").read_text(), root)
        for filename, content in (("switch-macos.txt", cross), ("native-macos.txt", native)):
            write_changed(out / filename, content)
        (out / "tools").mkdir(exist_ok=True)
        archiver = out / "tools/ar"
        archiver.write_text('#!/bin/sh\nexec /opt/devkitpro/devkitA64/bin/aarch64-none-elf-ar "$@"\n')
        archiver.chmod(0o755)
        for source, target in (("bindgen-switch-wrapper.sh", "bindgen"),
                               ("rustc-switch-wrapper.sh", "rustc"),
                               ("bindgen-atomic-shim.h", "bindgen-atomic-shim.h")):
            text = (src / source).read_text()
            text = text.replace("*sanity_check_for_rust.rs*|*sanitycheckrs.rs*)",
                                "*sanity_check_for_rust.rs*|*sanitycheckrs.rs*|*/meson-private/sanity.rs)")
            path = out / "tools" / target
            path.write_text(text)
            path.chmod(0o755)
        compat = out / "compat/lib"
        compat.mkdir(parents=True, exist_ok=True)
        # Link names required by Rust's Linux std; implementations already live
        # in pinned src/nouveau/vulkan/rust_switch_stubs.c. No global SDK writes.
        for name in ("dl", "rt", "util"):
            subprocess.run(["/opt/devkitpro/devkitA64/bin/aarch64-none-elf-ar", "rcs",
                            str(compat / f"lib{name}.a")], check=True)
        include = out / "install/opt/devkitpro/portlibs/switch/include"
        for name in ("vulkan", "vk_video"):
            shutil.copytree(src / "include" / name, include / name, dirs_exist_ok=True)
        print("Pinned headers staged:", include, flush=True)
    for name, command in commands:
        stage = "native" if name.startswith(("translator-", "native-")) else "cross"
        if args.stage not in ("all", stage) and not (args.stage == "install" and name == "install"):
            continue
        if name == "install" and args.stage == "cross":
            continue
        if name in ("native-configure", "cross-configure") and (out / stage / "build.ninja").is_file():
            command = command[:2] + ["--reconfigure"] + command[2:]
        print(name + ": " + shlex.join(command), flush=True)
        with (out / f"{name}.log").open("a") as log:
            log.write("\n$ " + shlex.join(command) + "\n")
            log.flush()
            result = subprocess.run(command, env=env_native if stage == "native" else env_cross,
                                    stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"{name} exited {result.returncode}; see {out}/{name}.log")
    if args.stage in ("all", "install", "verify"):
        manifest = verify_install(root)
        print(f"Verified {len(manifest['libraries'])} Switch archives; {out}/manifest.json", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        import sys
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
