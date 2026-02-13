import os
import re
import subprocess
import warnings
from pathlib import Path
from typing import Match, Optional

DOCS_ROOT = "https://ps-stage.rozert.cloud"


def tag_link(tag: str) -> str:
    return f"{DOCS_ROOT}/redoc/public/#tag/{tag}"


CONF = {
    "links": {
        "api-docs": f"{DOCS_ROOT}/redoc/public",
        "api.paypal": tag_link("PayPal"),
        "api.paycash": tag_link("PayCash"),
        "api.appex": tag_link("Appex"),
        "transaction.response": tag_link("Transactions/operation/transaction_retrieve"),
    },
}


def find_code_snippet(snippet_name: str, project_root: Path) -> Optional[str]:
    """Находит код между маркерами BEGIN и END в проекте."""
    pattern = f"# BEGIN {snippet_name}\n(.*?)# END {snippet_name}"
    regex = re.compile(pattern, re.DOTALL)

    found_snippets = []
    for root, dirs, files in os.walk(project_root):
        # Игнорируем node_modules
        if "node_modules" in dirs:
            dirs.remove("node_modules")

        for file in files:
            if file.endswith((".py", ".js", ".ts", ".html", ".css")):
                file_path = Path(root) / file
                content = file_path.read_text()
                matches = regex.finditer(content)
                for match in matches:
                    found_snippets.append((file_path, match.group(1).strip()))

    if len(found_snippets) > 1:
        warning_msg = f"Found multiple snippets for '{snippet_name}' in files:\n"
        for file_path, _ in found_snippets:
            warning_msg += f"  - {file_path}\n"
        warnings.warn(warning_msg)

    return found_snippets[0][1] if found_snippets else None


def replace_snippet(match: Match) -> str:  # type: ignore[type-arg]
    """Заменяет плейсхолдер сниппета на найденный код."""
    snippet_name = match.group(1).strip()
    code = find_code_snippet(snippet_name, Path(__file__).parent.parent)
    assert code, f"Snippet '{snippet_name}' not found in the project."
    return code or f"<!-- Snippet {snippet_name} not found -->"


def replace_link(match: Match) -> str:  # type: ignore[type-arg]
    """Заменяет плейсхолдер ссылки на markdown ссылку."""
    link_key = match.group(1).strip()
    link_text = match.group(2).strip()
    print(link_key, link_text)  # noqa
    print(f"{link_key=}")  # noqa
    url = CONF["links"][link_key]
    return f"[{link_text}]({url})"


def process_placeholders(content: str, project_root: Path) -> str:
    """Обрабатывает плейсхолдеры в контенте."""
    # Обработка сниппетов
    snippet_pattern = r"%%snippet\s+([^%]+)%%"
    content = re.sub(snippet_pattern, replace_snippet, content)

    # Обработка ссылок
    link_pattern = r"%%link\s+(\S+)\s+([^%]+)%%"
    content = re.sub(link_pattern, replace_link, content)

    return content


def main() -> None:
    docs_dir = Path(__file__).parent
    project_root = docs_dir.parent
    generated_dir = docs_dir / "rozert-python-client/docs"

    # Создаем директорию для сгенерированных файлов
    generated_dir.mkdir(exist_ok=True)

    # Обрабатываем все md файлы
    for md_file in docs_dir.glob("*.md"):
        content = md_file.read_text()
        processed_content = process_placeholders(content, project_root)

        # Сохраняем обработанный файл
        output_file = generated_dir / md_file.name
        output_file.write_text(processed_content)
        print(f"Processed {md_file.name} -> {output_file.name}")  # noqa

    # Commit and push docs
    subprocess.check_call(
        f"""
cd {docs_dir}/rozert-python-client && \
git commit -a -m "Update docs";
git push
    """,
        shell=True,
    )


if __name__ == "__main__":
    main()
