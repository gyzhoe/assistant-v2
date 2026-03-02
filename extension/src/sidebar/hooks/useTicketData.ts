import { useEffect, useRef } from 'react'
import { useSidebarStore } from '../store/sidebarStore'
import type { ContentToSidebarMessage } from '../../shared/messages'

export function useTicketData(): void {
  const setTicketData = useSidebarStore((s) => s.setTicketData)
  const setIsTicketPage = useSidebarStore((s) => s.setIsTicketPage)
  const restoreReplyForTicket = useSidebarStore((s) => s.restoreReplyForTicket)
  const prevTicketUrlRef = useRef<string | null>(null)

  useEffect(() => {
    // Request current ticket data on mount
    chrome.runtime.sendMessage({ type: 'REQUEST_TICKET_DATA' }).catch(() => {})

    const listener = (message: ContentToSidebarMessage) => {
      if (message.type === 'TICKET_DATA_UPDATED') {
        const newUrl = message.payload.ticketUrl
        setTicketData(message.payload)
        setIsTicketPage(true)

        // Restore cached reply when navigating to a different ticket
        if (newUrl && newUrl !== prevTicketUrlRef.current) {
          prevTicketUrlRef.current = newUrl
          const currentReply = useSidebarStore.getState().reply
          if (!currentReply) {
            restoreReplyForTicket(newUrl)
          }
        }
      } else if (message.type === 'NOT_A_TICKET_PAGE') {
        prevTicketUrlRef.current = null
        setTicketData(null)
        setIsTicketPage(false)
      }
    }

    chrome.runtime.onMessage.addListener(listener)
    return () => chrome.runtime.onMessage.removeListener(listener)
  // setTicketData, setIsTicketPage, and restoreReplyForTicket are stable Zustand setters — safe to omit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
