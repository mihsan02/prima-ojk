with open('prima-backend/app.py', 'r') as f:
    content = f.read()

old = 'def load_pakd():\n    try:\n        if os.path.exists(DATA_FILE):\n            with open(DATA_FILE, "r") as f:\n                data = json.load(f)\n            if data:\n                return [_migrate_record(p) for p in data]\n    except Exception:\n        pass\n    return [dict(p) for p in PAKD_DEFAULT]\n\n\n\n\ndef save_pakd(data):\n    dir_ = os.path.dirname(DATA_FILE) or "."\n    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")\n    try:\n        with os.fdopen(fd, "w") as f:\n            json.dump(data, f, indent=2)\n        os.replace(tmp_path, DATA_FILE)\n    except Exception:\n        try:\n            os.unlink(tmp_path)\n        except OSError:\n            pass\n        raise'

new = open('/workspaces/prima-ojk/new_db_functions.py').read()

assert old in content, "String tidak ditemukan"
content = content.replace(old, new)
with open('prima-backend/app.py', 'w') as f:
    f.write(content)
print("Done")
