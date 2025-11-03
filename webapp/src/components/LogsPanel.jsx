import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Terminal, Download, CheckCircle2, XCircle, Clock } from 'lucide-react'

export default function LogsPanel({ currentJob, socket }) {
  const logsEndRef = useRef(null)

  useEffect(() => {
    // Auto-scroll to bottom when new logs arrive
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [currentJob?.logs])

  const handleDownload = (filename) => {
    if (!currentJob?.job_id) return
    
    // Auto-detect server URL (same logic as App.jsx)
    const getServerURL = () => {
      if (import.meta.env.VITE_SIGNALING_SERVER_URL) {
        return import.meta.env.VITE_SIGNALING_SERVER_URL
      }
      if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        return 'http://localhost:10000'
      }
      return 'https://neurax-server.onrender.com'
    }
    
    const SERVER_URL = getServerURL()
    window.open(`${SERVER_URL}/download/${currentJob.job_id}/${filename}`, '_blank')
  }

  return (
    <div className="glass rounded-lg p-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <Terminal className="w-5 h-5 text-neon-blue" />
        <h2 className="text-lg font-semibold">Logs & Output</h2>
      </div>

      {/* Job Info */}
      {currentJob && (
        <div className="glass-strong p-3 rounded-lg mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Job Status</span>
            {currentJob.status === 'completed' ? (
              <CheckCircle2 className="w-4 h-4 text-green-400" />
            ) : currentJob.status === 'failed' ? (
              <XCircle className="w-4 h-4 text-red-400" />
            ) : (
              <Clock className="w-4 h-4 text-blue-400 animate-spin" />
            )}
          </div>
          
          <div className="space-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-gray-400">Mode:</span>
              <span className="text-gray-200">{currentJob.mode?.toUpperCase()}</span>
            </div>
            {currentJob.runtime && (
              <div className="flex justify-between">
                <span className="text-gray-400">Runtime:</span>
                <span className="text-gray-200">{currentJob.runtime.toFixed(2)}s</span>
              </div>
            )}
            {currentJob.exit_code !== null && (
              <div className="flex justify-between">
                <span className="text-gray-400">Exit Code:</span>
                <span
                  className={
                    currentJob.exit_code === 0 ? 'text-green-400' : 'text-red-400'
                  }
                >
                  {currentJob.exit_code}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Logs Container */}
      <div className="flex-1 overflow-y-auto bg-black/30 rounded-lg p-3 font-mono text-sm mb-4">
        {!currentJob || !currentJob.logs || currentJob.logs.length === 0 ? (
          <div className="text-gray-500 text-center py-8">
            <p>No logs yet</p>
            <p className="text-xs mt-2">Run a task to see logs here</p>
          </div>
        ) : (
          <div className="space-y-1">
            <AnimatePresence>
              {currentJob.logs.map((log, idx) => (
                <motion.div
                  key={idx}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={`${
                    log.includes('[ERROR]') || log.includes('ERROR')
                      ? 'text-red-400'
                      : log.includes('[DEPENDENCY]')
                      ? 'text-yellow-400'
                      : log.includes('[EXECUTE]')
                      ? 'text-green-400'
                      : 'text-gray-300'
                  }`}
                >
                  {log}
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={logsEndRef} />
          </div>
        )}
      </div>

      {/* Output Files */}
      {currentJob?.output_files && currentJob.output_files.length > 0 && (
        <div className="glass-strong p-3 rounded-lg">
          <div className="text-sm font-medium mb-2">Output Files</div>
          <div className="space-y-2">
            {currentJob.output_files.map((file, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between p-2 bg-black/20 rounded"
              >
                <span className="text-xs text-gray-300">{file}</span>
                <button
                  onClick={() => handleDownload(file)}
                  className="p-1 text-neon-blue hover:text-neon-purple transition-colors"
                >
                  <Download className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Task Info */}
      {currentJob && (
        <div className="mt-4 text-xs text-gray-500">
          <div className="flex items-center gap-2 mb-1">
            <span>Job ID:</span>
            <span className="font-mono text-gray-400">
              {currentJob.job_id?.slice(0, 16)}...
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
