# 🚂 Railway Deployment Guide - Placement AI Backend

## 📋 Prerequisites
- GitHub account
- Railway account (sign up at https://railway.app with GitHub)
- Your code pushed to a GitHub repository

## 🚀 Step-by-Step Deployment

### Step 1: Prepare Your Repository

1. **Initialize Git (if not already done)**
   ```bash
   cd d:\App\placement-AI\backend
   git init
   git add .
   git commit -m "Initial commit for Railway deployment"
   ```

2. **Create a GitHub repository**
   - Go to https://github.com/new
   - Name it: `placement-ai-backend`
   - Don't initialize with README (you already have files)
   - Click "Create repository"

3. **Push to GitHub**
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/placement-ai-backend.git
   git branch -M main
   git push -u origin main
   ```

### Step 2: Deploy on Railway

1. **Go to Railway Dashboard**
   - Visit https://railway.app
   - Click "Login" and sign in with GitHub

2. **Create New Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Authorize Railway to access your repositories
   - Select `placement-ai-backend` repository

3. **Railway will automatically detect your Python app and start building**
   - It reads `Procfile` and `requirements.txt`
   - Build takes 5-10 minutes (PyTorch is large)

### Step 3: Configure Environment Variables

1. **In Railway Dashboard, click on your service**
2. **Go to "Variables" tab**
3. **Add all variables from your `.env` file:**

```
PERPLEXITY_API_KEY=your_perplexity_api_key
GEMINI_API=your_gemini_api_key
MONGODB_URI=your_mongodb_connection_string
MONGODB_DB=Placement_Ai
MONGODB_COLLECTION=Resume
MONGO_URI=your_mongodb_connection_string
MONGODB_DB_N8N=n8n
MONGODB_COLLECTION_QUIZ=quiz_test
MONGODB_COLLECTION_QUIZ_ANALYSIS=quiz_analysis
EMAIL_PASSWORD=your_email_password
N8N_ROADMAP_WEBHOOK=your_n8n_webhook_url
N8N_MOBILE_WEBHOOK=your_n8n_mobile_webhook_url
N8N_TEST_GENERATION_WEBHOOK=your_n8n_test_webhook_url
N8N_TEST_ANSWER_WEBHOOK=your_n8n_answer_webhook_url
N8N_TEST_ANSWER_RESPONSE_WEBHOOK=your_n8n_response_webhook_url
N8N_WEEKLY_TEST_WEBHOOK=your_n8n_weekly_test_webhook_url
N8N_PROGRESS_TRACKING_WEEKLY_WEBHOOK=your_n8n_progress_webhook_url
N8N_MONTHLY_TEST_WEBHOOK=your_n8n_monthly_test_webhook_url
N8N_MONTHLY_ANALYSIS_WEBHOOK=your_n8n_monthly_analysis_webhook_url
RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
```

4. **Click "Add Variable" for each one**

### Step 4: Generate Public URL

1. **In your service, go to "Settings" tab**
2. **Scroll to "Networking" section**
3. **Click "Generate Domain"**
4. **You'll get a URL like:** `https://your-app-name.up.railway.app`

### Step 5: Test Your Deployment

1. **Check deployment logs** in the "Deployments" tab
2. **Test your API:**
   ```bash
   curl https://your-app-name.up.railway.app/api/health
   ```

3. **Common endpoints to test:**
   - `/api/health` - Health check
   - `/api/domains` - Get domains
   - `/api/roles/<domain>` - Get roles

### Step 6: Update Frontend Configuration

Once deployed, update your frontend to use the Railway backend URL:

1. In your frontend code, replace:
   ```javascript
   const API_URL = "http://localhost:5000"
   ```
   
   With:
   ```javascript
   const API_URL = "https://your-app-name.up.railway.app"
   ```

## 📊 Monitoring & Maintenance

### Check Logs
- Go to Railway dashboard → Your service → "Deployments" tab
- Click on latest deployment to see real-time logs

### Monitor Usage
- Railway gives $5 free credit per month
- Check usage in "Settings" → "Usage"
- Each hour of runtime costs ~$0.01

### Redeploy
- Push changes to GitHub:
  ```bash
  git add .
  git commit -m "Update backend"
  git push
  ```
- Railway auto-deploys on push!

## ⚠️ Important Notes

### Memory Management
- Your app uses PyTorch (memory-heavy)
- If it crashes due to memory, upgrade to Railway Pro
- Or optimize by removing unused models

### Cold Starts
- Railway free tier may sleep after inactivity
- First request after sleep takes 10-30 seconds
- Keep active with health check pings

### File Storage
- `.pkl` model files are included in deployment
- Any files uploaded by users are ephemeral (disappear on restart)
- Use external storage (S3, Cloudinary) for user uploads

### Database
- MongoDB Atlas is already external ✅
- No changes needed

## 🔧 Troubleshooting

### Build Fails
**Error:** `Out of memory`
- Reduce requirements.txt (remove unused packages)
- Split large dependencies

**Error:** `torch installation failed`
- Railway should handle this automatically
- Check `nixpacks.toml` is present

### App Crashes
**Error:** `Memory limit exceeded`
- Upgrade to Railway Pro ($5/month for 512MB→8GB)
- Or optimize code to use less memory

**Error:** `Port binding failed`
- Ensure you're using `$PORT` environment variable
- Procfile should have: `--bind 0.0.0.0:$PORT`

### Can't Connect
- Check if domain is generated in Settings → Networking
- Verify environment variables are set
- Check deployment logs for errors

## 💰 Cost Estimation

**Free Tier ($5 credit/month):**
- ~500 hours of runtime (24/7 for ~20 days)
- Unlimited bandwidth
- Automatic SSL

**If you exceed free tier:**
- Railway Pro: $5/month execution time fee
- Pay-as-you-go: Usage-based pricing

## 🎯 Next Steps

1. ✅ Backend deployed on Railway
2. 📦 Deploy frontend on Vercel
3. 🔗 Connect them with environment variables
4. 🧪 Test complete flow
5. 🚀 Go live!

**Need help with Vercel frontend deployment?** Let me know!

---

## 📞 Support

**Railway Docs:** https://docs.railway.app
**Community:** https://discord.gg/railway
**Status:** https://status.railway.app
