import zipfile
import xml.etree.ElementTree as ET
import sys

def get_docx_text(path):
    namespaces = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    }
    
    try:
        with zipfile.ZipFile(path) as docx:
            document_xml = docx.read('word/document.xml')
            root = ET.fromstring(document_xml)
            
            paragraphs = []
            for p in root.findall('.//w:p', namespaces):
                texts = []
                for t in p.findall('.//w:t', namespaces):
                    if t.text:
                        texts.append(t.text)
                if texts:
                    paragraphs.append(''.join(texts))
                else:
                    paragraphs.append('')
            return '\n'.join(paragraphs)
    except Exception as e:
        return f"Error reading {path}: {str(e)}"

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python extract_docx.py <path_to_docx>")
        sys.exit(1)
    
    print(get_docx_text(sys.argv[1]))
