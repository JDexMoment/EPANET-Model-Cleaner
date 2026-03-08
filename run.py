import sys
from pathlib import Path

# Добавляем корень проекта в пути поиска модулей
sys.path.append(str(Path(__file__).parent))

from src.ui.gui import AppGUI

def main():
    app = AppGUI()
    app.run()

if __name__ == "__main__":
    main()