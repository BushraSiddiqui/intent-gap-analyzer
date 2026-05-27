# Deploy Guide — for non-technical users

This guide gets your tool live on the internet (free, public URL) in about **15 minutes**. No coding, no terminal, no Git. You'll use Hugging Face Spaces, which is the friendliest free host for Streamlit apps.

## What you'll end up with

A public URL like `https://huggingface.co/spaces/yourname/intent-gap-analyzer` that anyone can visit. Each visitor gets **3 free analyses per day** (using your shared Gemini key). If they want more, they paste their own free Gemini key in the sidebar — unlimited from there.

## Before you start

You need:
- A web browser (Chrome / Safari / anything)
- An email address you can check
- 15 minutes

That's it. No software to install.

---

## Step 1: Make a Hugging Face account (2 min)

1. Open https://huggingface.co in your browser.
2. Click **Sign Up** in the top-right corner.
3. Use your email. Pick a username — it will appear in your tool's URL, so pick something simple like `your-name`. Avoid special characters.
4. Open your inbox, click the verification link they send you.
5. You're in. Leave this tab open.

## Step 2: Get a free Gemini API key (3 min)

This is the brain of the tool. The free version gives 1500 requests per day.

1. Open a **new tab** and go to https://aistudio.google.com/app/apikey
2. Sign in with any Google account.
3. Click **Create API key**, then **Create API key in new project**.
4. A long string starting with `AIzaSy...` appears. Click the copy icon next to it.
5. Paste it into a temporary note (Notes app, Stickies, anywhere safe) — you'll need it in Step 5.

## Step 3: Create your Space (2 min)

Back in the Hugging Face tab:

1. Click your profile picture (top right) → **New Space**.
2. Fill in the form:
   - **Owner**: your username (already set)
   - **Space name**: `intent-gap-analyzer` (or whatever you like — lowercase, no spaces, use hyphens)
   - **License**: pick **MIT** from the dropdown
   - **Select the Space SDK**: click the **Docker** card. (HF no longer has a Streamlit card — Docker is the right choice; the project includes a `Dockerfile` that handles the Streamlit setup for you.)
   - **Docker template**: pick **Blank** if asked
   - **Space hardware**: leave as **CPU basic · 2 vCPU · 16 GB · FREE**
   - **Public** vs **Private**: pick **Public** (so others can use it) or **Private** (just for you)
3. Click the **Create Space** button at the bottom.

You land on a near-empty page with tabs at the top: **App · Files · Community · Settings**.

## Step 4: Upload the files (3 min)

1. Click the **Files** tab.
2. Click the **Add file** button (top right) → **Upload files**.
3. A file picker opens. You need to upload **every file** from the `intent-gap-analyzer` folder. The fastest way:
   - Open the `intent-gap-analyzer` folder on your computer
   - Select ALL files and subfolders inside it (`Cmd+A` on Mac, `Ctrl+A` on Windows)
   - Drag them into the Hugging Face upload area
4. Hugging Face will show a list of files to be uploaded. It MUST include:
   - `Dockerfile` (no extension — important!)
   - `streamlit_app.py`
   - `analyze.py`
   - `requirements.txt`
   - `README.md`
   - Everything inside the `src/` folder (intent_extractor.py, serp_crawler.py, llm_crawler.py, gap_analyzer.py, report_builder.py, rate_limit.py, __init__.py)
   - The `templates/` folder with `report.html.j2` inside

   If `Dockerfile` is missing, the build will fail — double-check it's in the list.
5. In the **Commit message** box at the bottom, type: `initial upload`
6. Click **Commit changes to main**.

Hugging Face now starts building your app. This takes **2–5 minutes the first time**. You'll see a yellow "Building" badge near the top.

## Step 5: Add your Gemini API key as a secret (1 min)

While the build is running, paste your Gemini key as a secret so the app can use it.

1. Click the **Settings** tab.
2. Scroll down to the section called **Variables and secrets**.
3. Click **New secret**.
4. **Name**: type exactly `GEMINI_API_KEY` (all caps, with the underscores — this is critical)
5. **Value**: paste the long Gemini key you copied in Step 2
6. Click **Save**.
7. Scroll up and click **Restart Space** (or **Factory rebuild** if you see it). The Space will rebuild with the secret in place.

## Step 6: Use your app (1 min)

1. Click the **App** tab.
2. Wait until the yellow "Building" badge turns green ("Running"). Refresh if needed.
3. You should see your tool's interface: a sidebar on the left with a key field, and a main area with **Target URL**, **Keywords**, and an **Analyze** button.
4. Test it: paste a URL (e.g. one of your zeronorth.com pages), type 1–2 keywords, click **Analyze**.
5. Watch the progress bar. After 30–90 seconds, you'll see the results.

Your tool is now live at:
```
https://huggingface.co/spaces/your-username/intent-gap-analyzer
```

Share that URL with anyone.

---

## How the free trial works

- Each visitor (identified by IP) can run **3 analyses per day** on your shared Gemini key.
- After that, they see a message: "Paste your own free Gemini key for unlimited runs."
- The limit resets every day at midnight UTC.
- Anyone who pastes their own key skips the limit entirely. Your key is never used for them.

Note: the daily counter is stored in temporary memory and resets if the Space restarts (which happens after 48h of inactivity on the free tier). This is fine — it just means the limit is approximate.

---

## Troubleshooting

**Build fails (red badge)** — Click the **Logs** tab and scroll to the bottom. The error is usually obvious. Most common causes:
- `Dockerfile` missing or named wrong (must be exactly `Dockerfile`, no `.txt` extension, capital D)
- A Python file is missing or has the wrong name
- Go back to Step 4 and re-upload anything missing

**Space stays "Building" forever** — Docker builds on the free tier can take 5–8 minutes the first time. After that, rebuilds are faster (1–2 min). Be patient on the first build.

**"No API key configured"** — You forgot Step 5, or the secret name isn't exactly `GEMINI_API_KEY` (case-sensitive). Go to Settings → Variables and secrets and check.

**Analysis fails on SERP step** — Cloud IPs get blocked by Google and Bing. The Gemini + DuckDuckGo Chat parts still work (you'll still get LLM citation data). To fix the SERP side, sign up for a free SerpAPI key (100 searches/month free) — ask me to help you swap it in.

**Space is "sleeping"** — Free Spaces sleep after 48 hours of no visitors. The first visit after sleep takes 30 seconds to wake up. Totally normal.

**Wrong URL or app doesn't load** — In the **App** tab, click the small icon to "Open in new tab" — sometimes the embed has issues but the real URL works.

---

## When you want to change something

1. Go to your Space → **Files** tab.
2. Click the file you want to edit (e.g. `streamlit_app.py`).
3. Click the **pencil icon** (edit) in the top right of the file view.
4. Make your changes.
5. Scroll down, add a commit message like `update sidebar text`, click **Commit changes**.
6. The Space rebuilds automatically in 2–3 minutes.

That's the whole workflow. No Git, no terminal, no install.
