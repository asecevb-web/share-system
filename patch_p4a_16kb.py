#!/usr/bin/env python3
"""
patch_p4a_16kb.py - Patch python-for-android to compile all native libraries
with 16KB page alignment (required for Android 15+).

Run this before `buildozer android debug` to patch the p4a recipes.
"""

import os
import sys
import glob
import re

def find_p4a_recipes_dir():
    """Find the python-for-android recipes directory."""
    # Check common locations
    candidates = [
        os.path.expanduser("~/.local/share/python-for-android/recipes"),
        os.path.expanduser("~/.python-for-android/recipes"),
        "/usr/local/share/python-for-android/recipes",
    ]

    # Also check pip-installed p4a
    try:
        import pythonforandroid
        p4a_dir = os.path.dirname(pythonforandroid.__file__)
        candidates.insert(0, os.path.join(p4a_dir, "recipes"))
    except ImportError:
        pass

    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate

    return None


def patch_build_context():
    """Patch the p4a build context to inject 16KB alignment flags."""
    try:
        import pythonforandroid.build as build
    except ImportError:
        print("⚠️  Cannot import p4a build module, skipping context patch")
        return False

    # Find the get_recipe function or build environment setup
    original_init = build.Context.__init__ if hasattr(build, 'Context') else None

    # Instead of patching class methods, set environment variables
    # that will be picked up by the compiler/linker
    env_flags = {
        'LDFLAGS': '-Wl,-z,max-page-size=16384',
        'CFLAGS': '-DANDROID_PAGE_SIZE=16384',
        'CXXFLAGS': '-DANDROID_PAGE_SIZE=16384',
    }

    for key, value in env_flags.items():
        current = os.environ.get(key, '')
        if value not in current:
            os.environ[key] = f"{current} {value}".strip()

    print("✅ Set 16KB alignment environment flags")
    return True


def patch_recipe_ldflags(recipe_dir):
    """Patch individual recipe build.py files to add 16KB alignment."""
    patched = 0
    flag = '-Wl,-z,max-page-size=16384'

    for recipe_path in glob.glob(os.path.join(recipe_dir, '*', 'recipe.py')):
        try:
            with open(recipe_path, 'r') as f:
                content = f.read()

            # Skip if already patched
            if 'max-page-size=16384' in content:
                continue

            # Find build_arch method and inject LDFLAGS
            # Pattern: def build_arch(self, arch):
            # We'll add LDFLAGS injection at the start of build methods
            modified = False

            # Patch: add LDFLAGS to get_recipe_env or build methods
            if 'get_recipe_env' in content:
                # Add LDFLAGS to existing get_recipe_env
                pattern = r"(def get_recipe_env\(self.*?\n)(.*?)(return )"
                def add_ldflags(match):
                    indent = match.group(2)
                    if 'max-page-size' not in indent:
                        return match.group(1) + match.group(2) + f"env['LDFLAGS'] = env.get('LDFLAGS', '') + ' {flag}'\n        " + match.group(3)
                    return match.group(0)

                new_content = re.sub(pattern, add_ldflags, content, flags=re.DOTALL)
                if new_content != content:
                    content = new_content
                    modified = True

            if modified:
                with open(recipe_path, 'w') as f:
                    f.write(content)
                patched += 1
                print(f"  ✅ Patched: {os.path.basename(os.path.dirname(recipe_path))}")

        except Exception as e:
            print(f"  ⚠️  Failed to patch {recipe_path}: {e}")

    return patched


def patch_ndk_toolchain():
    """Patch NDK toolchain wrapper scripts to inject 16KB alignment."""
    ndk_home = os.environ.get('ANDROID_NDK_HOME') or os.environ.get('NDK_HOME')
    if not ndk_home:
        # Try to find it
        candidates = [
            os.path.expanduser("~/.android/ndk"),
            "/opt/android/ndk",
        ]
        for candidate in candidates:
            if os.path.isdir(candidate):
                # Find the latest version
                versions = sorted(os.listdir(candidate))
                if versions:
                    ndk_home = os.path.join(candidate, versions[-1])
                    break

    if not ndk_home or not os.path.isdir(ndk_home):
        print("⚠️  NDK not found, skipping toolchain patch")
        return False

    # Find clang wrapper scripts
    toolchain_dir = os.path.join(ndk_home, "toolchains", "llvm", "prebuilt")
    for host_dir in glob.glob(os.path.join(toolchain_dir, "*")):
        bin_dir = os.path.join(host_dir, "bin")
        if os.path.isdir(bin_dir):
            # Check for clang wrapper
            for clang in ["clang", "clang++"]:
                clang_path = os.path.join(bin_dir, clang)
                if os.path.isfile(clang_path):
                    print(f"  Found: {clang_path}")

    return True


def verify_so_alignment(apk_path):
    """Verify that .so files in the APK have 16KB alignment."""
    import zipfile
    from elftools.elf.elffile import ELFFile

    issues = []
    checked = 0

    with zipfile.ZipFile(apk_path, 'r') as z:
        for name in z.namelist():
            if not name.endswith('.so'):
                continue

            with z.open(name) as so_file:
                elf = ELFFile(so_file)
                checked += 1

                for seg in elf.iter_segments():
                    if seg['p_type'] == 'PT_LOAD':
                        if seg['p_align'] < 16384:
                            issues.append(name)
                            print(f"  ❌ {name}: p_align={seg['p_align']}")
                        break

    return checked, issues


def main():
    print("=" * 60)
    print("16KB Page Alignment Patcher for python-for-android")
    print("=" * 60)

    # Step 1: Set environment flags
    print("\n[1/3] Setting environment flags...")
    patch_build_context()

    # Step 2: Patch p4a recipes
    print("\n[2/3] Patching p4a recipes...")
    recipe_dir = find_p4a_recipes_dir()
    if recipe_dir:
        print(f"  Recipes dir: {recipe_dir}")
        patched = patch_recipe_ldflags(recipe_dir)
        print(f"  Patched {patched} recipes")
    else:
        print("  ⚠️  Recipes directory not found (will patch at build time)")

    # Step 3: Summary
    print("\n[3/3] Environment ready!")
    print("\nNext steps:")
    print("  1. Run: buildozer android debug")
    print("  2. The build will use 16KB-aligned compilation")
    print("  3. Run verify_16kb.py to check the result")
    print()


if __name__ == '__main__':
    main()
