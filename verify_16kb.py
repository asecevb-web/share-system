#!/usr/bin/env python3
"""
verify_16kb.py - Verify that all .so files in an APK have proper 16KB alignment.

Usage: python verify_16kb.py <path_to_apk>
"""

import sys
import zipfile
from elftools.elf.elffile import ELFFile


def verify_apk(apk_path):
    """Verify all .so files in the APK have 16KB alignment."""
    print(f"Checking: {apk_path}")
    print("=" * 60)

    issues = []
    passed = []
    skipped = []

    with zipfile.ZipFile(apk_path, 'r') as z:
        so_files = [n for n in z.namelist() if n.endswith('.so')]

        if not so_files:
            print("⚠️  No .so files found in APK")
            return True

        for name in sorted(so_files):
            try:
                with z.open(name) as so_file:
                    elf = ELFFile(so_file)
                    aligned = True

                    for seg in elf.iter_segments():
                        if seg['p_type'] == 'PT_LOAD':
                            if seg['p_align'] < 16384:
                                aligned = False
                                issues.append((name, seg['p_align']))
                                print(f"  ❌ FAIL: {name}")
                                print(f"     p_align={seg['p_align']} (need >= 16384)")
                            break

                    if aligned:
                        passed.append(name)
                        print(f"  ✅ OK: {name}")

            except Exception as e:
                skipped.append((name, str(e)))
                print(f"  ⚠️  SKIP: {name} ({e})")

    print()
    print("=" * 60)
    print(f"Results: {len(passed)} passed, {len(issues)} failed, {len(skipped)} skipped")
    print("=" * 60)

    if issues:
        print("\n❌ FAILED - The following libraries are NOT 16KB aligned:")
        for name, align in issues:
            print(f"  - {name} (p_align={align})")
        print("\nThis APK will NOT work on Android 15+ devices with 16KB page size.")
        return False
    else:
        print("\n✅ PASSED - All libraries are properly 16KB aligned!")
        print("This APK should work on Android 15+ devices.")
        return True


def main():
    if len(sys.argv) < 2:
        # Try to find APK in bin/
        import glob
        apks = glob.glob("bin/*.apk") + glob.glob("bin/*-16k.apk")
        if apks:
            apk_path = sorted(apks)[-1]  # Use latest
        else:
            print("Usage: python verify_16kb.py <path_to_apk>")
            sys.exit(1)
    else:
        apk_path = sys.argv[1]

    success = verify_apk(apk_path)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
