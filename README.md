# Streamlit + Supabase Boilerplate

This repository contains the foundation for a Streamlit application connected to a Supabase database, ready to be deployed on Google Cloud Run.

## Local Setup Instructions

1. **Install Dependencies:**
   Install the required Python packages using `pip`:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up Environment Variables:**
   - Copy the provided `.env.example` file and rename the copy to `.env`.
   - Open `.env` and fill in your actual Supabase project URL and API key.
     ```bash
     SUPABASE_URL=https://your-project-id.supabase.co
     SUPABASE_KEY=eyJh...
     ```
   - *Note: The `.env` file should never be committed to version control. It is automatically loaded by the application for local development via `python-dotenv`.*

3. **Database Configuration:**
   - Open `app.py` and replace `[NOM_DE_LA_TEVA_TAULA]` with the actual name of an existing table in your Supabase database to allow the health check to succeed.

4. **Run the Application:**
   Start the Streamlit development server:
   ```bash
   streamlit run app.py
   ```

## Production Deployment (Google Cloud Run)

The application handles `os.environ` fallback natively and expects standard `PORT`, `SUPABASE_URL`, and `SUPABASE_KEY` variables to be supplied by the Cloud Run environment.

* Ensure you provide the `--server.port=$PORT` argument to Streamlit or specify it in your `Dockerfile` when deploying.
