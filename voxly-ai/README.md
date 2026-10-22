# Voxly AI — Interactive 3D Voice Employee Landing Page

> An interactive, enterprise-grade landing page featuring **Voxly**, a real-time 3D AI voice employee. Built around the **Hero UI** design system as its aesthetic and interactive anchor—uniting living 3D character embodiment, sub-500ms Web Audio synthesis, disciplined typography, and Emil Kowalski craft principles.

![Voxly Preview](/public/images/VoxlyBot_preview.png)

---

## ✨ Features

- **🤖 Interactive 3D Robot Mascot (Voxly)**:
  - 3D skeletal rig with animated morph targets, facial expressions (`HAPPY`, `EXCITED`, `THINKING`, `SURPRISED`, `ANGRY`).
  - Procedural arm gestures: friendly single-hand wave, double-hand wave, and 360° celebratory barrel roll.
  - Interactive palm tracking facing the user directly ($+Z$ normal alignment).
  - Smooth cursor tracking with gentle head/body rotation (up to $\pm 60^\circ$).
- **🗣️ Voice & Audio Synthesis**:
  - Web Speech API integration with voice personality and sound effects.
  - Real-time Web Audio API frequency visualizer and mic analyzer.
  - Interactive "Live Mic Chat" modal for conversational AI demonstration.
- **⚡ Autonomous Sequence & Interactive Dialogue**:
  - Auto-play demonstration loop with dialogue bubble for hands-free showcase.
  - Section-aware observer that resets cleanly when scrolling back to the Hero.
  - Responsive multi-click progression with friendly and humorous reactions.
- **💼 Comprehensive Product Showcase**:
  - **Hero Section**: Live 3D robot, quick action chips, and CTAs.
  - **Interactive Workflow Builder**: Visual node configuration for AI call flows.
  - **Live Call Simulator**: Simulated incoming customer calls with audio wave animation.
  - **Knowledge & Training Center**: Multi-source document and prompt training interface.
  - **Enterprise Platform Grid**: Scalability, sub-500ms latency, CRM integrations.
  - **Live Analytics Dashboard**: Real-time resolution metrics and sentiment graphs.
  - **Transparent Pricing**: Scalable tier comparisons.
  - **Interactive FAQ**: Accordion-based answers to common enterprise questions.

---

## 🛠️ Tech Stack

- **Framework**: React 18 + Vite
- **3D Engine**: Three.js + React Three Fiber (`@react-three/fiber`, `@react-three/drei`)
- **Styling**: Tailwind CSS + Custom Glassmorphism & Animations
- **Icons**: Lucide React
- **Audio**: Web Audio API + SpeechSynthesis API

---

## 🚀 Getting Started

### Prerequisites
- Node.js (v18 or higher)
- npm or pnpm

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/saiskm115/voxly-ai.git
   cd voxly-ai
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start local development server:
   ```bash
   npm run dev
   ```
   Open `http://localhost:5173/` in your browser.

4. Build for production:
   ```bash
   npm run build
   ```

---

## 🔌 Connecting With Your Backend

The user console is architected to interface directly with your separate backend:

### 1. Configure Your Backend API URL
In your `.env` or environment:
```bash
VITE_API_URL=http://localhost:8000/api
```
*(Point this to your backend server URL. If left blank, the frontend uses an internal simulator so pages remain interactive).*

### 2. Supported Backend Endpoints
All user console actions route through the clean API client in `src/services/api.js`:
- **Auth & Sessions**: `POST /api/auth/login`, `POST /api/auth/signup`, `POST /api/auth/google`, `POST /api/auth/github`, `GET /api/auth/session`, `POST /api/auth/logout`
- **AI Voice Employees**: `GET /api/agents`, `POST /api/agents`, `GET /api/agents/:id`, `PUT /api/agents/:id`, `DELETE /api/agents/:id`
- **Telephony & Virtual DIDs**: `GET /api/telephony/numbers`, `POST /api/telephony/buy`, `POST /api/telephony/numbers/:id/assign`, `PUT /api/telephony/numbers/:id/routing`
- **Calls & Transcripts**: `GET /api/calls`, `GET /api/calls/:id`, `POST /api/calls/outbound`
- **CRM Leads & Pipeline**: `GET /api/leads`, `POST /api/leads`, `PATCH /api/leads/:id/stage`
- **Campaigns**: `GET /api/campaigns`, `POST /api/campaigns`, `PATCH /api/campaigns/:id/status`
- **Billing & Wallet**: `GET /api/billing/wallet`, `POST /api/billing/topup`

---

## 📄 License

MIT License — feel free to use and customize for your own projects!
