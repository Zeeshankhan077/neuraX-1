# NeuraX Universal Cloud Compute - WebApp

Modern React frontend for NeuraX Cloud Compute System with glassmorphism UI.

## 🚀 Quick Start

### Development

```bash
cd webapp
npm install
npm run dev
```

Opens at `http://localhost:3000`

### Build for Production

```bash
npm run build
npm run preview
```

## 🏗️ Tech Stack

- **React 18** - UI Framework
- **Vite** - Build tool
- **TailwindCSS** - Styling
- **Framer Motion** - Animations
- **Monaco Editor** - Code editing
- **Socket.IO Client** - Real-time communication
- **Lucide React** - Icons

## 📁 Structure

```
webapp/
├── src/
│   ├── components/
│   │   ├── Sidebar.jsx       # Left sidebar with nodes/history
│   │   ├── CodeEditor.jsx   # Center code editor panel
│   │   └── LogsPanel.jsx    # Right logs/output panel
│   ├── App.jsx               # Main app component
│   ├── main.jsx              # Entry point
│   └── index.css             # Global styles
├── public/                   # Static assets
├── package.json
├── vite.config.js
└── tailwind.config.js
```

## ⚙️ Configuration

Create `.env` file:

```env
VITE_SIGNALING_SERVER_URL=http://localhost:10000
```

For production, set to your deployed server URL:
```env
VITE_SIGNALING_SERVER_URL=https://neurax-server.onrender.com
```

## 🚢 Render Deployment

1. **Root Directory**: `webapp`
2. **Build Command**: `npm install && npm run build`
3. **Start Command**: `npm run preview`
4. **Environment Variables**: 
   - `VITE_SIGNALING_SERVER_URL` - Backend server URL

## 🎨 Features

- ✅ Three-panel dashboard layout
- ✅ Monaco code editor with syntax highlighting
- ✅ File upload (drag-drop) for Blender/AutoCAD
- ✅ Real-time log streaming
- ✅ Job status tracking
- ✅ Compute node monitoring
- ✅ Glassmorphism UI with neon effects
- ✅ Dark theme
- ✅ Responsive design

## 📱 Usage

1. **AI Mode**: Write Python code, click "Run Task"
2. **Blender Mode**: Upload `.blend` file, add arguments, run
3. **AutoCAD Mode**: Upload `.dwg` file, add arguments, run
4. **Custom Mode**: Enter CLI command, run

All jobs execute in Docker sandbox with live logs!

