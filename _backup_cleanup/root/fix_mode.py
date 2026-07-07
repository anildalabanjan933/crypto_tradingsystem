content = open('run_optimization.py', 'r').read()
old = '    mode_choice = int(input("Select mode (1 or 2): "))
if mode_choice not in [1, 2]:
    print("Invalid choice. Please enter 1 or 2.")
    return'
new = '    mode_choice = int(input("Select mode (1 or 2): "))\n    if mode_choice not in [1, 2]:\n        print("Invalid choice. Please enter 1 or 2.")\n        return'
open('run_optimization.py', 'w').write(content.replace(old, new))
print('Done')
