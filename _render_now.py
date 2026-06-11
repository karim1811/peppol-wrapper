from jinja2 import Environment, FileSystemLoader
from pathlib import Path

env = Environment(loader=FileSystemLoader(str(Path(r'C:\Users\karim\Desktop\projet facture peppol\programme\templates'))))
html = env.get_template('index.html').render()
out = Path(r'C:\Users\karim\Desktop\projet facture peppol\programme\static\index_render.html')
out.write_text(html, encoding='utf-8')
print(out)
print(html)
