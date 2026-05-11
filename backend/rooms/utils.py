import re
from urllib.parse import parse_qs, urlparse

import validators


def parse_video_url(raw: str) -> dict:
    """
    Возвращает режим воспроизведения и URL для фронтенда.
    """
    url = (raw or "").strip()
    if not url or not validators.url(url):
        raise ValueError("Некорректная ссылка")

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    # YouTube
    if "youtube.com" in host or "youtu.be" in host:
        vid = _youtube_id(url, parsed)
        if not vid:
            raise ValueError("Не удалось определить ролик YouTube")
        embed = f"https://www.youtube.com/embed/{vid}?enablejsapi=1&origin=*"
        return {
            "provider": "youtube",
            "embed_url": embed,
            "stream_url": "",
            "extra": {"video_id": vid},
        }

    # Rutube
    if "rutube.ru" in host:
        vid = _rutube_id(url, parsed)
        if not vid:
            raise ValueError("Не удалось определить ролик Rutube")
        embed = f"https://rutube.ru/play/embed/{vid}/"
        return {
            "provider": "rutube",
            "embed_url": embed,
            "stream_url": "",
            "extra": {"video_id": vid},
        }

    # VK video (встраивание через vk.com/video_ext.php)
    if "vk.com" in host or "vkvideo.ru" in host:
        oid, vid = _vk_ids(url)
        if oid and vid is not None:
            embed = f"https://vk.com/video_ext.php?oid={oid}&id={vid}&hd=2&autoplay=0"
            return {
                "provider": "vk",
                "embed_url": embed,
                "stream_url": "",
                "extra": {"oid": oid, "id": vid},
            }

    # Прямая ссылка на файл
    path = (parsed.path or "").lower()
    if any(path.endswith(ext) for ext in (".mp4", ".webm", ".ogg", ".m3u8", ".mpd")):
        return {
            "provider": "direct",
            "embed_url": "",
            "stream_url": url,
            "extra": {},
        }

    raise ValueError(
        "Формат ссылки не поддерживается. Укажите Rutube, YouTube, VK или прямую ссылку на видеофайл."
    )


def _youtube_id(url: str, parsed) -> str | None:
    if "youtu.be" in (parsed.netloc or "").lower():
        return (parsed.path or "").strip("/").split("/")[0] or None
    qs = parse_qs(parsed.query)
    if "v" in qs and qs["v"]:
        return qs["v"][0]
    m = re.search(r"youtube\.com/embed/([^/?]+)", url)
    if m:
        return m.group(1)
    return None


def _rutube_id(url: str, parsed) -> str | None:
    m = re.search(r"/play/embed/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/video/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/shorts/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    return None


def _vk_ids(url: str) -> tuple[str | None, int | None]:
    m = re.search(r"video(-?\d+)_(\d+)", url)
    if m:
        return m.group(1), int(m.group(2))
    m = re.search(r"z=video(-?\d+)_(\d+)", url)
    if m:
        return m.group(1), int(m.group(2))
    return None, None
