import { useState, useRef } from 'react'
import { motion } from 'framer-motion'
import Editor from '@monaco-editor/react'
import { useDropzone } from 'react-dropzone'
import { Upload, Play, FileCode, Sparkles } from 'lucide-react'

export default function CodeEditor({ onSubmit, currentJob }) {
  const [code, setCode] = useState(`# Welcome to NeuraX Cloud Compute
# Enter your Python code here

import math

# Example: Calculate factorial
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(10)
print(f"Factorial of 10 = {result}")
`)
  const [mode, setMode] = useState('ai')
  const [command, setCommand] = useState('')
  const [args, setArgs] = useState('')
  const [uploadedFile, setUploadedFile] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        setUploadedFile(acceptedFiles[0])
      }
    },
    accept: {
      'text/x-python': ['.py'],
      'application/zip': ['.zip'],
      'application/x-blender': ['.blend'],
      'application/acad': ['.dwg']
    }
  })

  const handleSubmit = async () => {
    if (isSubmitting) return

    setIsSubmitting(true)
    
    try {
      await onSubmit({
        mode,
        code: mode === 'ai' ? code : '',
        file: uploadedFile,
        command: mode === 'custom' ? command : '',
        args
      })
    } catch (error) {
      console.error('Submit error:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="glass rounded-lg p-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <FileCode className="w-5 h-5 text-neon-blue" />
          <h2 className="text-lg font-semibold">Code Editor</h2>
        </div>
        
        {/* Mode Selector */}
        <div className="flex gap-2">
          {['ai', 'blender', 'autocad', 'custom'].map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-3 py-1 text-sm rounded-lg transition-all ${
                mode === m
                  ? 'bg-neon-blue/30 text-neon-blue border border-neon-blue/50'
                  : 'bg-white/5 text-gray-400 hover:text-gray-200'
              }`}
            >
              {m.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Code Editor or File Upload */}
      {mode === 'ai' && (
        <div className="flex-1 mb-4 code-editor-container">
          <Editor
            height="100%"
            defaultLanguage="python"
            value={code}
            onChange={(value) => setCode(value || '')}
            theme="vs-dark"
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: 'on',
              roundedSelection: false,
              scrollBeyondLastLine: false,
              automaticLayout: true
            }}
          />
        </div>
      )}

      {/* File Upload Zone */}
      {(mode === 'blender' || mode === 'autocad') && (
        <div className="flex-1 mb-4">
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all ${
              isDragActive
                ? 'border-neon-blue bg-neon-blue/10'
                : 'border-gray-600 hover:border-gray-500'
            }`}
          >
            <input {...getInputProps()} />
            <Upload className="w-12 h-12 mx-auto mb-4 text-gray-400" />
            {uploadedFile ? (
              <div>
                <p className="text-green-400">✓ {uploadedFile.name}</p>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    setUploadedFile(null)
                  }}
                  className="mt-2 text-sm text-red-400 hover:text-red-300"
                >
                  Remove
                </button>
              </div>
            ) : (
              <div>
                <p className="text-gray-400 mb-2">
                  {isDragActive
                    ? 'Drop file here'
                    : `Drag & drop ${mode === 'blender' ? '.blend' : '.dwg'} file here`}
                </p>
                <p className="text-sm text-gray-500">or click to browse</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Custom Command Input */}
      {mode === 'custom' && (
        <div className="flex-1 mb-4 space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Command</label>
            <input
              type="text"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="echo Hello"
              className="w-full px-4 py-2 glass rounded-lg border border-white/10 focus:border-neon-blue focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Arguments</label>
            <input
              type="text"
              value={args}
              onChange={(e) => setArgs(e.target.value)}
              placeholder="--flag value"
              className="w-full px-4 py-2 glass rounded-lg border border-white/10 focus:border-neon-blue focus:outline-none"
            />
          </div>
        </div>
      )}

      {/* Additional Args for all modes */}
      {(mode === 'blender' || mode === 'autocad') && (
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">Additional Arguments</label>
          <input
            type="text"
            value={args}
            onChange={(e) => setArgs(e.target.value)}
            placeholder="--format PNG --resolution 1920x1080"
            className="w-full px-4 py-2 glass rounded-lg border border-white/10 focus:border-neon-blue focus:outline-none"
          />
        </div>
      )}

      {/* Self-Test Button */}
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={async () => {
          setIsSubmitting(true)
          const testCode = `# NeuraX Self-Test
print('NeuraX Local Test Successful!')
print('✅ All systems operational')
print('Server: Connected')
print('Compute Node: Ready')
result = 42 + 8
print(f'Calculation test: 42 + 8 = {result}')
print('✅ Task Finished Successfully')`
          setCode(testCode)
          setMode('ai')
          await onSubmit({
            mode: 'ai',
            code: testCode,
            file: null,
            command: '',
            args: ''
          })
          setIsSubmitting(false)
        }}
        disabled={isSubmitting}
        className="mb-2 w-full flex items-center justify-center gap-2 px-4 py-2 bg-gradient-to-r from-green-500/20 to-emerald-500/20 border border-green-500/50 rounded-lg text-green-400 hover:from-green-500/30 hover:to-emerald-500/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Sparkles className="w-4 h-4" />
        <span>Run Self-Test</span>
      </motion.button>

      {/* Submit Button */}
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onClick={handleSubmit}
        disabled={isSubmitting || (mode === 'blender' && !uploadedFile) || (mode === 'autocad' && !uploadedFile)}
        className="neon-button w-full flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isSubmitting ? (
          <>
            <Sparkles className="w-5 h-5 animate-spin" />
            <span>Processing...</span>
          </>
        ) : (
          <>
            <Play className="w-5 h-5" />
            <span>Run Task</span>
          </>
        )}
      </motion.button>

      {/* Current Job Status */}
      {currentJob && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 glass-strong p-3 rounded-lg"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm">Job: {currentJob.job_id?.slice(0, 8)}...</span>
            <span
              className={`text-xs px-2 py-1 rounded ${
                currentJob.status === 'completed'
                  ? 'bg-green-500/20 text-green-400'
                  : currentJob.status === 'running'
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'bg-gray-500/20 text-gray-400'
              }`}
            >
              {currentJob.status}
            </span>
          </div>
          {currentJob.runtime && (
            <div className="text-xs text-gray-400 mt-1">
              Runtime: {currentJob.runtime.toFixed(2)}s
            </div>
          )}
        </motion.div>
      )}
    </div>
  )
}
