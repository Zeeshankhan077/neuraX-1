import { useState, useEffect } from 'react'
import { io } from 'socket.io-client'
import Sidebar from './components/Sidebar'
import CodeEditor from './components/CodeEditor'
import LogsPanel from './components/LogsPanel'
import { motion } from 'framer-motion'
import { Zap } from 'lucide-react'

// Auto-detect local vs production
// If running on localhost, use local server; otherwise use Render production
const getServerURL = () => {
  // Check for explicit environment variable override
  if (import.meta.env.VITE_SIGNALING_SERVER_URL) {
    return import.meta.env.VITE_SIGNALING_SERVER_URL
  }
  
  // Auto-detect: if on localhost, use local server
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'http://localhost:10000'
  }
  
  // Otherwise use production server
  return 'https://neurax-server.onrender.com'
}

const SERVER_URL = getServerURL()

function App() {
  const [socket, setSocket] = useState(null)
  const [connected, setConnected] = useState(false)
  const [computeNodes, setComputeNodes] = useState([])
  const [currentJob, setCurrentJob] = useState(null)
  const [jobHistory, setJobHistory] = useState([])

  useEffect(() => {
    // Initialize Socket.IO connection
    const newSocket = io(SERVER_URL, {
      transports: ['websocket', 'polling']
    })

    newSocket.on('connect', () => {
      console.log('Connected to server')
      setConnected(true)
      setSocket(newSocket)
      
      // Request compute nodes list
      newSocket.emit('get_compute_nodes')
    })

    newSocket.on('disconnect', () => {
      console.log('Disconnected from server')
      setConnected(false)
    })

    newSocket.on('compute_nodes_list', (nodes) => {
      setComputeNodes(nodes)
    })

    newSocket.on('compute_node_registered', (node) => {
      setComputeNodes(prev => [...prev, node])
    })

    newSocket.on('job_status', (data) => {
      if (data.job_id === currentJob?.job_id) {
        setCurrentJob(prev => ({ ...prev, ...data }))
      }
      // Update job history
      setJobHistory(prev => {
        const existing = prev.find(j => j.job_id === data.job_id)
        if (existing) {
          return prev.map(j => j.job_id === data.job_id ? { ...j, ...data } : j)
        }
        return [...prev, data]
      })
    })

    newSocket.on('job_log', (data) => {
      if (currentJob && data.job_id === currentJob.job_id) {
        setCurrentJob(prev => ({
          ...prev,
          logs: [...(prev.logs || []), data.log]
        }))
      }
    })

    return () => {
      newSocket.close()
    }
  }, [])

  const handleJobSubmit = async (jobData) => {
    if (!socket || !connected) {
      alert('Not connected to server')
      return
    }

    try {
      // If file is provided, upload it first
      let filePath = ''
      if (jobData.file) {
        const formData = new FormData()
        formData.append('file', jobData.file)
        
        const uploadResponse = await fetch(`${SERVER_URL}/upload`, {
          method: 'POST',
          body: formData
        })
        
        const uploadData = await uploadResponse.json()
        filePath = uploadData.file_path
      }

      // Submit job
      const response = await fetch(`${SERVER_URL}/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          mode: jobData.mode,
          code: jobData.code,
          file_path: filePath,
          command: jobData.command,
          args: jobData.args
        })
      })

      const result = await response.json()
      
      if (result.job_id) {
        // Subscribe to job logs
        socket.emit('subscribe_job_logs', { job_id: result.job_id })
        
        setCurrentJob({
          job_id: result.job_id,
          status: 'queued',
          mode: jobData.mode,
          logs: [],
          runtime: null,
          exit_code: null
        })

        // Poll for job status
        const pollInterval = setInterval(async () => {
          const statusResponse = await fetch(`${SERVER_URL}/status/${result.job_id}`)
          const statusData = await statusResponse.json()
          
          setCurrentJob(prev => ({ ...prev, ...statusData }))
          
          if (statusData.status === 'completed' || statusData.status === 'failed') {
            clearInterval(pollInterval)
          }
        }, 1000)
      }
    } catch (error) {
      console.error('Job submission error:', error)
      alert(`Error: ${error.message}`)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-800">
      {/* Header */}
      <motion.header
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="glass-strong border-b border-white/10 p-4"
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Zap className="w-8 h-8 text-neon-blue" />
            <h1 className="text-2xl font-bold bg-gradient-to-r from-neon-blue to-neon-purple bg-clip-text text-transparent">
              NeuraX
            </h1>
            <span className="text-sm text-gray-400">Universal Cloud Compute</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
            <span className="text-sm text-gray-300">
              {connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>
      </motion.header>

      {/* Main Layout - Three Panels */}
      <div className="max-w-7xl mx-auto p-4 grid grid-cols-12 gap-4 h-[calc(100vh-80px)]">
        {/* Left Sidebar */}
        <motion.div
          initial={{ x: -20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="col-span-2"
        >
          <Sidebar
            connected={connected}
            computeNodes={computeNodes}
            jobHistory={jobHistory}
          />
        </motion.div>

        {/* Center - Code Editor */}
        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="col-span-7"
        >
          <CodeEditor
            onSubmit={handleJobSubmit}
            currentJob={currentJob}
          />
        </motion.div>

        {/* Right Panel - Logs */}
        <motion.div
          initial={{ x: 20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="col-span-3"
        >
          <LogsPanel
            currentJob={currentJob}
            socket={socket}
          />
        </motion.div>
      </div>
    </div>
  )
}

export default App
