interface Session {
  id: string
  name: string
}

interface SessionEvent {
  id: number
  timestamp: number
  type: string
}

interface EventDetail {
  id: number
  data: unknown
}

export async function fetchSessions(): Promise<Session[]> {
  try {
    const response = await fetch('/api/sessions')
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('fetchSessions error:', error)
    return []
  }
}

export async function fetchSessionEvents(id: string): Promise<SessionEvent[]> {
  try {
    const response = await fetch(`/api/sessions/${id}/events`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('fetchSessionEvents error:', error)
    return []
  }
}

export async function fetchEventDetail(id: number): Promise<EventDetail | null> {
  try {
    const response = await fetch(`/api/events/${id}`)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    return await response.json()
  } catch (error) {
    console.error('fetchEventDetail error:', error)
    return null
  }
}

export function openStream(
  onMessage: (data: unknown) => void,
  onError?: (error: Event) => void,
  onClose?: (event: CloseEvent) => void
): WebSocket {
  const ws = new WebSocket(`${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`)

  ws.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data)
      onMessage(data)
    } catch (error) {
      console.error('Failed to parse WebSocket message:', error)
    }
  })

  if (onError) {
    ws.addEventListener('error', onError)
  }

  if (onClose) {
    ws.addEventListener('close', onClose)
  }

  return ws
}
