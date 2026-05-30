import requests
import re

# путь к плейлисту
M3U_FILE = "NightTV.m3u"


def get_token():
    """Получение нового токена peers.tv"""
    url = "https://api.peers.tv/auth/2/token"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://peers.tv/",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "inetra:anonymous",
        "client_id": "29783051",
        "client_secret": "b4d4eb438d760da95f0acb5bc6b5c760"
    }

    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()

    token = response.json()["access_token"]
    return token


def update_m3u(token):
    """Замена token= в m3u файле"""
    with open(M3U_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # заменяем token=...
    new_content = re.sub(
        r'(token=)[^&\s]+',
        r'\1' + token,
        content
    )

    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)


def main():
    print("Получаю новый токен...")

    token = get_token()

    print("Обновляю плейлист...")
    update_m3u(token)

    print("Готово ✅")
    print("Новый токен:", token)


if __name__ == "__main__":
    main()
