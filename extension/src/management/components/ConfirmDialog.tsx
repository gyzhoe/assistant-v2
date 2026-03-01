import * as AlertDialog from '@radix-ui/react-alert-dialog'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Yes, delete',
  onConfirm,
  onCancel,
}: ConfirmDialogProps): React.ReactElement {
  const container = document.querySelector('.app-shell') as HTMLElement | null

  return (
    <AlertDialog.Root open={open} onOpenChange={isOpen => { if (!isOpen) onCancel() }}>
      <AlertDialog.Portal container={container}>
        <AlertDialog.Overlay className="confirm-overlay" />
        <AlertDialog.Content className="confirm-content">
          <AlertDialog.Title className="confirm-title">{title}</AlertDialog.Title>
          <AlertDialog.Description className="confirm-desc">{description}</AlertDialog.Description>
          <div className="confirm-actions">
            <AlertDialog.Cancel asChild>
              <button type="button" className="secondary-btn" onClick={onCancel}>
                Cancel
              </button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <button type="button" className="primary-btn confirm-danger" onClick={onConfirm}>
                {confirmLabel}
              </button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
