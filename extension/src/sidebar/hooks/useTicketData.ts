import { useEffect } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import type { ContentToSidebarMessage } from '../../shared/messages'

export function useTicketData(): void {
  const setTicketData = useSidebarStore((s) => s.setTicketData)
  const setIsTicketPage = useSidebarStore((s) => s.setIsTicketPage)

  useEffect(() => {
    // Request current ticket data on mount
    chrome.runtime.sendMessage({ type: 'REQUEST_TICKET_DATA' }).catch(() => {})

    const listener = (message: ContentToSidebarMessage) => {
      if (message.type === 'TICKET_DATA_UPDATED') {
        setTicketData(message.payload)
        setIsTicketPage(true)
      } else if (message.type === 'NOT_A_TICKET_PAGE') {
        setTicketData(null)
        setIsTicketPage(false)
      }
    }

    chrome.runtime.onMessage.addListener(listener)
    return () => chrome.runtime.onMessage.removeListener(listener)
  // setTicketData and setIsTicketPage are stable Zustand setters — safe to omit from deps.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
