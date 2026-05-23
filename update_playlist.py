import re
import requests

FILE_PATH = "NightTV.m3u"  # Имя твоего файла в репозитории


def get_peers_token():
    """Получение свежего токена от Peers.tv"""
    url = "https://peers.tv"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://peers.tv",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "inetra:anonymous",
        "client_id": "29783051",
        "client_secret": "b4d4eb438d760da95f0acb5bc6b5c760",
    }
    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()["access_token"]


def main():
    try:
        print("🤖 Получаем новый токен от Peers.tv...")
        new_token = get_peers_token()

        print(f"📖 Читаем файл {FILE_PATH}...")
        try:
            with open(FILE_PATH, "r", encoding="utf-8") as f:
                current_content = f.read()
        except FileNotFoundError:
            print("🆕 Файл не найден. Будет создан новый файл.")
            current_content = f"#EXTM3U\n#EXTINF:-1,PeersTV\nhttp://example.com{new_token}"

        # Проверяем, изменился ли токен
        match = re.search(r"token=([^&\s]+)", current_content)
        if match:
            current_token = match.group(1)
            if current_token == new_token:
                print("🚫 Токен не изменился. Обновление не требуется.")
                return
        else:
            print("⚠️ Старый токен не найден. Заменяем везде.")

        print("✏️ Токен изменился! Обновляем текст плейлиста...")
        updated_content = re.sub(
            r"(token=)[^&\s]+", r"\1" + new_token, current_content
        )

        with open(FILE_PATH, "w", encoding="utf-8") as f:
            f.write(updated_content)

        print("✅ Файл успешно обновлен локально.")

    except Exception as e:
        print(f"💥 Ошибка: {e}")
        exit(1)  # Завершаем с ошибкой, чтобы GitHub Actions показал красный крестик


if __name__ == "__main__":
    main()
