import re

def find_section_headers(content):
    return re.findall(r'^# +(.*)$', content, re.MULTILINE)

def group_by_sections(content, section_headers):
    sections = {}
    current_section = None
    for line in content.split('\n'):
        if line.startswith('#'):
            current_section = line.strip()
        else:
            if current_section:
                sections[current_section].append(line)
            else:
                sections['Unassigned'].append(line)
    return sections

def print_sections(sections):
    for section, lines in sections.items():
        print(f'# {section}')
        for line in lines:
            print(line)
        print()

if __name__ == '__main__':
    with open('guide.txt', 'r') as f:
        content = f.read()
        section_headers = find_section_headers(content)
        sections = group_by_sections(content, section_headers)
        print_sections(sections)