export interface Mark {
  id: string
  x: number
  y: number
  bbox: [number, number, number, number] | null
  source: 'auto' | 'manual'
  confidence: number | null
  is_modified: boolean
}

export interface Photo {
  id: string
  original_name: string
  width: number
  height: number
  uploaded_at: string
  captured_at: string
  timezone: string
  image_url: string
  original_url: string
}

export interface PhotoRecord extends Photo {
  head_count: number
  thumbnail_url: string
  detection_status: string
  model_version: string | null
  detection_config: Record<string, unknown> | null
  initial_detections: Mark[]
  created_at: string
  updated_at: string
  version: number
  marks: Mark[]
}

export interface Health {
  status: string
  timezone: string
  model: { ready: boolean; name: string | null; provider: string; error: string | null }
}

export interface JobResult {
  marks: Mark[]
  model_version: string
  config: Record<string, unknown>
  elapsed_seconds: number
}

export interface DetectionJob {
  id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'interrupted'
  error: string | null
  result: JobResult | null
}
