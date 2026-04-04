#!/bin/bash
set -euo pipefail

# --- CONFIGURATION ---
PROJECT_ID="projectprt"
REGION="asia-southeast1"
SERVICE_NAME="backend-api"
REPO_NAME="backend-repo" # ชื่อที่เก็บ Image ใหม่
INSTANCE_CONNECTION_NAME="projectprt:asia-southeast1:prt-sql-dev"

# ⚠️ กรุณาแก้ค่าเหล่านี้ให้ตรงกับของคุณ
DB_USER="prt_app"         
DB_PASSWORD="Pao_122546"    # <--- อย่าลืมใส่รหัสผ่าน DB ตรงนี้ (ถ้ายังไม่ได้ใส่)
DB_NAME="prt"              

# GCS / Auth config (ให้ตรงกับ .env ของคุณ)
GCS_BUCKET_NAME="acct-docs-dev"
GCS_BASE_PATH="prt"
SIGNED_URL_EXPIRATION_SECONDS="604800"
GOOGLE_CLOUD_PROJECT="$PROJECT_ID"
GOOGLE_APPLICATION_CREDENTIALS="/app/service-account.json"
GOOGLE_CLIENT_ID="886029565568-fc4i9cgm7s07kf9p5vv9g49kpsie1kh1.apps.googleusercontent.com"

# URL แบบใหม่สำหรับ Artifact Registry (asia-southeast1-docker.pkg.dev)
IMAGE_URL="asia-southeast1-docker.pkg.dev/$PROJECT_ID/$REPO_NAME/$SERVICE_NAME"
IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"
IMAGE_REF="$IMAGE_URL:$IMAGE_TAG"

# สร้าง Connection String
DB_URL="postgresql://$DB_USER:$DB_PASSWORD@/$DB_NAME?host=/cloudsql/$INSTANCE_CONNECTION_NAME"

echo "========================================================"
echo "🚀 Starting Deployment for $SERVICE_NAME"
echo "   Project: $PROJECT_ID"
echo "   Region:  $REGION"
echo "   Image:   $IMAGE_REF"
echo "========================================================"

# 1. เปิด API ที่จำเป็น
echo "🔧 Enabling necessary services..."
gcloud services enable cloudbuild.googleapis.com run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com --project "$PROJECT_ID"

# 2. ตรวจสอบและสร้าง Artifact Registry Repository (ถ้ายังไม่มี)
echo "📦 Checking Artifact Registry Repository..."
if ! gcloud artifacts repositories describe "$REPO_NAME" --project="$PROJECT_ID" --location="$REGION" > /dev/null 2>&1; then
    echo "   Creating repository '$REPO_NAME'..."
    gcloud artifacts repositories create "$REPO_NAME" \
        --project="$PROJECT_ID" \
        --repository-format=docker \
        --location="$REGION" \
        --description="Docker repository for Backend API"
else
    echo "   Repository '$REPO_NAME' already exists."
fi

# 3. Build Container Image (ใช้ URL ใหม่)
echo "🏗️  Building Container Image..."
gcloud builds submit --tag "$IMAGE_REF" . --project "$PROJECT_ID"


# 4. Deploy ไปยัง Cloud Run
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE_REF" \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --add-cloudsql-instances "$INSTANCE_CONNECTION_NAME" \
  --set-env-vars "DATABASE_URL=$DB_URL" \
  --set-env-vars "USE_MOCK_DATA=false" \
  --set-env-vars "GCS_BUCKET_NAME=$GCS_BUCKET_NAME" \
  --set-env-vars "GCS_BASE_PATH=$GCS_BASE_PATH" \
  --set-env-vars "SIGNED_URL_EXPIRATION_SECONDS=$SIGNED_URL_EXPIRATION_SECONDS" \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT" \
  --set-env-vars "GOOGLE_APPLICATION_CREDENTIALS=$GOOGLE_APPLICATION_CREDENTIALS" \
  --set-env-vars "GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID" \
  --set-env-vars "SECRET_KEY=prt-secret-key-2025" \
  --port 8080

echo "========================================================"
echo "✅ DEPLOYMENT COMPLETE!"
echo "========================================================"
