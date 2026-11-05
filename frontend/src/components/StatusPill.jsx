
const findingStatusClasses = {
  'Open': 'finding-status-open',
  'Under Review': 'finding-status-under-review',
  'Resolved': 'finding-status-resolved',
}

const dossierStatusClasses = {
  'Draft': 'draft',
  'In Review': 'review',
  'Completed': 'completed',
}

export default function StatusPill({ status, variant = 'finding' }) {
  const statusClass =
    variant === 'dossier'
      ? dossierStatusClasses[status]
      : findingStatusClasses[status]

  return (
    <span
      className={
        variant === 'dossier'
          ? `dossier-status ${statusClass || ''}`
          : `finding-status ${statusClass || ''}`
      }
    >
      {status}
    </span>
  )
}
