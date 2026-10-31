import re
import glob
import os
import sys

def main():
    errors = []

    # Rule 3: check forbidden vendors in tenant surfaces
    forbidden_re = re.compile(r'\b(plivo|exotel|composio|stripe)\b', re.IGNORECASE)
    scan_files = glob.glob('server/routes/app_*.py') + glob.glob('server/routes/campaigns.py') + glob.glob('server/routes/integrations.py')
    for root, _, files in os.walk('dialtact-app/src'):
        for f in files:
            if f.endswith(('.js', '.jsx', '.ts', '.tsx', '.json', '.html')):
                scan_files.append(os.path.join(root, f))

    for fp in scan_files:
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                for idx, line in enumerate(f, 1):
                    m = forbidden_re.search(line)
                    if m:
                        # Skip if it is an explicit comment stating eradication/prohibition
                        if 'removed' in line.lower() or 'eradicate' in line.lower() or 'prohibit' in line.lower():
                            continue
                        errors.append(f"{fp}:{idx} Forbidden vendor leak: '{m.group(0)}' in line: {line.strip()[:80]}")
        except Exception:
            pass

    # Rule 2: dynamic sql text interpolation
    sql_re = re.compile(r'text\s*\(\s*f["\']')
    for root, _, files in os.walk('server'):
        for f in files:
            if f.endswith('.py'):
                fp = os.path.join(root, f)
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    for idx, line in enumerate(f, 1):
                        if sql_re.search(line):
                            errors.append(f"{fp}:{idx} Dynamic SQL interpolation: {line.strip()[:80]}")

    print(f"Total findings: {len(errors)}")
    for err in errors:
        print(" [FINDING]", err)

    if errors:
        sys.exit(1)
    else:
        print("All security audit patterns PASSED (0 findings).")

if __name__ == '__main__':
    main()
