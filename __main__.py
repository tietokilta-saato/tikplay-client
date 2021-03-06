#!/usr/bin/env python

import argparse
import hashlib
import json
import os
import os.path
import platform
import requests
import requests.exceptions
import sys

try:
    import pwd
    pwd_available = True
except ImportError:
    import getpass
    pwd_available = False


def whoami():
    # Prefer the pwd module, which is available only on Unix systems, as getpass relies on environment variables
    node = platform.node()
    if not node:
        node = "unknown"
    if pwd_available:
        return "{}@{}".format(pwd.getpwuid(os.getuid())[0], node)
    return "{}@{}".format(getpass.getuser(), node)


def wrap_request(method, *args_, **kwargs):
    data = None
    try:
        data = method(*args_, **kwargs)
        return data.json()
    except requests.exceptions.ConnectionError as e:
        print("Connection error: " + str(e))
    except ValueError as e:
        if data is not None:
            print("Invalid JSON received: " + data.text)
        else:
            print("An error occurred while constructing the request:")
            raise e


def format_time(secs):
    secs = int(secs)
    out = []
    if secs > 3600:
        hours, secs = divmod(secs, 3600)
        out.append("{}h".format(hours))
    if secs > 60:
        minutes, secs = divmod(secs, 60)
        out.append("{}m".format(minutes))
    out.append("{}s".format(secs))
    return " ".join(out)


def send_post(url, **kwargs):
    return wrap_request(requests.post, url, **kwargs)


def send_get(url, **kwargs):
    return wrap_request(requests.get, url, **kwargs)


def send_delete(url, **kwargs):
    return wrap_request(requests.delete, url, **kwargs)


def send_song(files, config):
    url_base = "http://" + config["host"] + "/srv/v1.0"
    for fn in files:
        data = {
            "user": whoami()
        }

        if config["verbose"]:
            print("Checking filename/URI {}".format(fn))

        # URI
        if not os.path.exists(fn):
            if type(fn) != str:
                data["url"] = fn.decode(errors="decode_backslashreplace")
            else:
                data["url"] = fn
            result = send_post(url_base + "/song", data=json.dumps(data))
            if result is not None:
                print(result["text"])
            return

        # File
        data["filename"] = os.path.basename(fn)
        song = open(fn, "rb")
        sha1 = hashlib.sha1(song.read()).hexdigest()
        data["url"] = "sha1:" + sha1
        result = send_post(url_base + "/song", data=json.dumps(data))
        if result is not None and not result["error"]:
            print(result["text"])
            continue

        print("File not found on the server, sending")
        song.seek(0)
        result = send_post(url_base + "/file", files={'file': ("upload." + fn.rsplit(".", 1)[-1], song)})
        if result is not None:
            if "saved" not in result or not result["saved"]:
                print("Error, file not saved: " + result["text"])
                return
            print("File sent successfully, adding to playlist")
            data["url"] = result["key"]
            result = send_post(url_base + "/song", data=json.dumps(data))
            if result is not None:
                print(result["text"])


def send_np(config):
    result = send_get("http://" + config["host"] + "/srv/v1.0/song")
    print("Now playing: {} - {} ({} seconds)".format(
        result["text"][0]["artist"],
        result["text"][0]["title"],
        result["text"][0]["time"])
    )


def send_playlist(_, config):
    result = send_get("http://" + config["host"] + "/srv/v1.0/queue/" + str(_))
    if result:
        for i, res in enumerate(result["text"]):
            if "artist" in res and "title" in res:
                song_name = "{} - {}".format(res["artist"], res["title"])
            elif "file" in res:
                song_name = res["file"]
            else:
                song_name = "unknown"
            if "time" in res:
                time_part = " ({})".format(format_time(res["time"]))
            else:
                time_part = ""
            print("Queue #{}: {}{}".format(i, song_name, time_part))


def send_skip(config):
    result = send_delete("http://" + config["host"] + "/srv/v1.0/song")
    print(result)


def send_clear(config):
    result = send_delete("http://" + config["host"] + "/srv/v1.0/queue")
    print(result)


def gen_config(target, **kwargs):
    with open(target, 'w') as f:
        json.dump(kwargs, f, indent=4)


if __name__ == "__main__":
    # Parse the arguments
    parser = argparse.ArgumentParser(prog="tikplay", description="tikplay - play that funky music")
    parser.add_argument('-v', '--verbose', action='store_true', help='be verbose for the gory details')
    parser.add_argument('-c', '--config', action='store', nargs=1, default=os.path.expanduser('~/.tikplayrc'),
                        help='specify the configuration file')

    sub = parser.add_subparsers(dest='cmd', help="sub-command help")
    play_parser = sub.add_parser('play', help='play a song')
    play_parser.add_argument('files', metavar='file/url', type=str, nargs='+', help='path to file or URL')
    np_parser = sub.add_parser('np', help='now playing')
    pl_parser = sub.add_parser('playlist', help='playlist')
    pl_parser.add_argument('n', default=10, type=int, help='amount of entries to fetch')
    del_parser = sub.add_parser('skip', help='skip song')
    clear_parser = sub.add_parser('clear', help='clear playlist')

    args = parser.parse_args(sys.argv[1:])
    if not os.path.exists(args.config):
        print("Error: The configuration file does not exist. Generating a default config to %s" % args.config)
        gen_config(args.config, verbose=True, host="tikradio.tt.hut.fi:5000")

    # Load the configuration
    with open(args.config, 'r') as fp:
        cfg = json.load(fp)

    cfg["verbose"] = args.verbose

    if args.cmd == "play":
        send_song(args.files, cfg)

    elif args.cmd == "np":
        send_np(cfg)

    elif args.cmd == "playlist":
        send_playlist(args.n, cfg)

    elif args.cmd == "skip":
        send_skip(cfg)

    elif args.cmd == "clear":
        send_clear(cfg)
