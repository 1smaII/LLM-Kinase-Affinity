from pathlib import Path
import hashlib, json, mimetypes, os, time
import oss2
from openai import OpenAI
from google import genai
from google.genai import types

ROOT = Path(__file__).parent


def img_file(ref, xlsx):
    p = Path(ref)
    p = p if p.is_absolute() else xlsx.parent / p
    p = p.resolve()
    if not p.is_file():
        raise FileNotFoundError(f"图片不存在：{p}")
    return p


def slot_text(img):
    pairs = [f"{a}={b}" if a and b else a or b for a, b in img["slots"]]
    return "Image_Slots: " + "; ".join(x for x in pairs if x)


def file_hash(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except Exception:
        return {}


def save_json(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def retry(fn, *args, tries=5, **kwargs):
    for i in range(tries):
        try:
            return fn(*args, **kwargs)
        except oss2.exceptions.RequestError:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def oss_bucket():
    auth = oss2.Auth(os.getenv("OSS_ACCESS_KEY_ID"), os.getenv("OSS_ACCESS_KEY_SECRET"))
    return oss2.Bucket(auth, os.getenv("OSS_ENDPOINT"), os.getenv("OSS_BUCKET"))


def oss_url(bucket, p, hours):
    key = file_hash(p)
    obj = f"model-images/{key}{p.suffix.lower() or '.png'}"
    if not retry(bucket.object_exists, obj):
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        retry(bucket.put_object_from_file, obj, str(p), headers={"Content-Type": mime})
    return bucket.sign_url("GET", obj, hours * 3600, slash_safe=True)


class Qwen:
    name = "qwen"

    def __init__(self, mode, cfg, max_tokens):
        self.mode, self.cfg, self.model, self.max_tokens = mode, cfg, cfg["model"], max_tokens
        self.client = OpenAI(api_key=os.getenv("QWEN_API_KEY"), base_url=cfg["base_url"])
        self.bucket = oss_bucket() if mode == "multimodal" else None

    def generate(self, prompt, text, images, xlsx):
        if self.mode == "text":
            messages = [{"role": "user", "content": f"{prompt}\n\n{text}"}]
        else:
            content = [{"type": "text", "text": f"{prompt}\n\n{text}"}]
            for img in images:
                mapping = slot_text(img)
                if mapping != "Image_Slots: ":
                    content.append({"type": "text", "text": mapping})
                url = oss_url(self.bucket, img_file(img["path"], xlsx), self.cfg["url_hours"])
                content.append({
                    "type": "image_url",
                    "image_url": {"url": url},
                    "max_pixels": self.cfg["max_pixels"],
                })
            messages = [{"role": "user", "content": content}]

        extra = {
    "enable_thinking": self.cfg["enable_thinking"]
}
if self.mode == "multimodal":
    extra["vl_high_resolution_images"] = self.cfg[
        "vl_high_resolution_images"
    ]

        r = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            extra_body=extra,
        )
        return (r.choices[0].message.content or "").strip()


class GPT:
    name = "gpt"

    def __init__(self, mode, cfg, max_tokens):
        self.mode, self.cfg, self.model, self.max_tokens = mode, cfg, cfg["model"], max_tokens
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=0)
        self.cache_file = ROOT / cfg["cache_file"]
        self.cache = load_json(self.cache_file)

    def upload(self, p):
        key = file_hash(p)
        if key in self.cache:
            return self.cache[key]
        with p.open("rb") as f:
            file_id = self.client.files.create(file=f, purpose="user_data").id
        self.cache[key] = file_id
        save_json(self.cache_file, self.cache)
        return file_id

    def generate(self, prompt, text, images, xlsx):
        content = [{"type": "input_text", "text": f"{prompt}\n\n{text}"}]

        if self.mode == "multimodal":
            for img in images:
                mapping = slot_text(img)
                if mapping != "Image_Slots: ":
                    content.append({"type": "input_text", "text": mapping})
                content.append({
                    "type": "input_image",
                    "file_id": self.upload(img_file(img["path"], xlsx)),
                    "detail": self.cfg["detail"],
                })

        r = self.client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": content}],
            reasoning={"effort": self.cfg["reasoning_effort"]},
            max_output_tokens=self.max_tokens,
            background=True,
        )

        print(f"GPT任务：{r.id}")
        while r.status in ("queued", "in_progress"):
            time.sleep(10)
            try:
                r = self.client.responses.retrieve(r.id)
            except Exception as e:
                print(f"GPT查询失败：{e}")

        if r.status != "completed":
            raise RuntimeError(f"GPT任务未完成：{r.status}")
        return (r.output_text or "").strip()


class Gemini:
    name = "gemini"

    def __init__(self, mode, cfg, max_tokens):
        self.mode, self.cfg, self.model, self.max_tokens = mode, cfg, cfg["model"], max_tokens
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.cache_file = ROOT / cfg["cache_file"]
        self.cache = load_json(self.cache_file)
        self.ttl = cfg["cache_hours"] * 3600

    def upload(self, p):
        key, now = file_hash(p), time.time()
        old = self.cache.get(key, {})
        if now - old.get("time", 0) < self.ttl and old.get("uri") and old.get("mime"):
            return old

        f = self.client.files.upload(file=str(p))
        while getattr(getattr(f, "state", None), "name", "") not in ("", "ACTIVE"):
            if getattr(getattr(f, "state", None), "name", "") == "FAILED":
                raise RuntimeError(f"Gemini 文件处理失败：{f.name}")
            time.sleep(2)
            f = self.client.files.get(name=f.name)

        item = {
            "uri": f.uri,
            "mime": f.mime_type or mimetypes.guess_type(p.name)[0] or "application/octet-stream",
            "time": now,
        }
        self.cache[key] = item
        save_json(self.cache_file, self.cache)
        return item

    @staticmethod
    def _norm(x):
        return " ".join(str(x or "").strip().casefold().replace("_", " ").split())

    @staticmethod
    def _is_validation_id(sid):
        s = str(sid or "").strip().casefold().replace("-", "_")
        return "_val_" in s or "_validation_" in s or s.startswith("val_") or s.startswith("validation_")

    def _validation_groups(self, text):
        data = json.loads(text)
        validation_ids = []

        for sheet in data.get("sheets", []):
            rows = sheet.get("rows", [])
            sheet_is_val = "val" in str(sheet.get("sheet_name", "")).casefold()
            for h, row in enumerate(rows):
                cols = [self._norm(x) for x in row]
                if "sample id" not in cols:
                    continue
                id_i = cols.index("sample id")
                for r in rows[h + 1:]:
                    if id_i >= len(r):
                        continue
                    sid = str(r[id_i] or "").strip()
                    if sid and (sheet_is_val or self._is_validation_id(sid)):
                        validation_ids.append(sid)
                break

        validation_ids = list(dict.fromkeys(validation_ids))
        if not validation_ids:
            return [text]

        groups = [
            validation_ids[i:i + self.validation_batch_size]
            for i in range(0, len(validation_ids), self.validation_batch_size)
        ]
        validation_set = set(validation_ids)
        outputs = []

        for group in groups:
            keep = set(group)
            chunk = json.loads(text)

            for sheet in chunk.get("sheets", []):
                rows = sheet.get("rows", [])
                for h, row in enumerate(rows):
                    cols = [self._norm(x) for x in row]
                    if "sample id" not in cols:
                        continue
                    id_i = cols.index("sample id")
                    filtered = rows[:h + 1]
                    for r in rows[h + 1:]:
                        sid = str(r[id_i] or "").strip() if id_i < len(r) else ""
                        if sid in validation_set and sid not in keep:
                            continue
                        filtered.append(r)
                    sheet["rows"] = filtered
                    break

            outputs.append(json.dumps(chunk, ensure_ascii=False, default=str, separators=(",", ":")))

        return outputs

    def _image_parts(self, images, xlsx):
        parts = []
        if self.mode != "multimodal":
            return parts

        resolution = {
            "low": types.PartMediaResolutionLevel.MEDIA_RESOLUTION_LOW,
            "medium": types.PartMediaResolutionLevel.MEDIA_RESOLUTION_MEDIUM,
            "high": types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
        }[self.cfg["media_resolution"]]

        for img in images:
            mapping = slot_text(img)
            if mapping != "Image_Slots: ":
                parts.append(types.Part.from_text(text=mapping))
            f = self.upload(img_file(img["path"], xlsx))
            parts.append(types.Part(
                file_data=types.FileData(file_uri=f["uri"], mime_type=f["mime"]),
                media_resolution=types.PartMediaResolution(level=resolution),
            ))
        return parts

    def _run_one_batch(self, prompt, chunk_text, image_parts, index, total):
        parts = [types.Part.from_text(text=f"{prompt}\n\n{chunk_text}")] + image_parts
        request = {
            "contents": [types.Content(role="user", parts=parts)],
            "config": {
                "max_output_tokens": self.max_tokens,
                "thinking_config": {"thinking_level": self.cfg["thinking_level"]},
            },
        }

        job = self.client.batches.create(model=self.model, src=[request])
        job_name = job.name
        print(f"Gemini Batch {index}/{total}：{job_name}")

        terminal_states = {
            "JOB_STATE_SUCCEEDED",
            "JOB_STATE_FAILED",
            "JOB_STATE_CANCELLED",
            "JOB_STATE_EXPIRED",
        }

        state = None
        while True:
            try:
                job = self.client.batches.get(name=job_name)
                state = job.state.name
                if state in terminal_states:
                    break
            except Exception as e:
                print(f"Gemini Batch 查询失败：{type(e).__name__}: {e}")
            time.sleep(30)

        if state != "JOB_STATE_SUCCEEDED":
            raise RuntimeError(f"Gemini Batch 未成功：{state}；错误：{getattr(job, 'error', None)}")

        item = job.dest.inlined_responses[0]
        if item.error:
            raise RuntimeError(f"Gemini Batch 请求失败：{item.error}")

        r = item.response
        result = (r.text or "").strip()
        candidate = r.candidates[0] if getattr(r, "candidates", None) else None
        finish_reason = getattr(getattr(candidate, "finish_reason", None), "name", "UNKNOWN")
        print(f"Gemini 第 {index}/{total} 组：{finish_reason}，输出 {len(result.splitlines())} 行")
        return result

    def generate(self, prompt, text, images, xlsx):
        chunks = self._validation_groups(text)
        image_parts = self._image_parts(images, xlsx)
        outputs = [
            self._run_one_batch(prompt, chunk, image_parts, i, len(chunks))
            for i, chunk in enumerate(chunks, start=1)
        ]

        if len(outputs) == 1:
            return outputs[0]

        header = "Sample_ID,Predicted_Kd_nM,Predicted_Label"
        merged = []
        for result in outputs:
            lines = [line.strip() for line in result.splitlines() if line.strip()]
            lines = [line for line in lines if not line.startswith("```")]
            if lines and lines[0].replace(" ", "") == header:
                lines = lines[1:]
            merged.extend(lines)

        return header + "\n" + "\n".join(merged)


def build_provider(name, mode, cfg, max_tokens):
    return {"qwen": Qwen, "gpt": GPT, "gemini": Gemini}[name](mode, cfg, max_tokens)
