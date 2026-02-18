import type { TicketData } from './types'

/** Messages sent from Content Script → Background SW → Sidebar */
export type ContentToSidebarMessage =
  | { type: 'TICKET_DATA_UPDATED'; payload: TicketData }
  | { type: 'INSERT_SUCCESS' }
  | { type: 'INSERT_FAILED'; payload: { reason: string } }
  | { type: 'NOT_A_TICKET_PAGE' }

/** Messages sent from Sidebar → Background SW → Content Script */
export type SidebarToContentMessage =
  | { type: 'INSERT_REPLY'; payload: { text: string } }
  | { type: 'REQUEST_TICKET_DATA' }

/** Union of all extension messages */
export type ExtensionMessage = ContentToSidebarMessage | SidebarToContentMessage
