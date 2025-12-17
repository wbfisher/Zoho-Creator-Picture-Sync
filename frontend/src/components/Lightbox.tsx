import { useEffect, useCallback, useState } from 'react'
import { useGalleryStore } from '@/store'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { formatBytes, formatDate } from '@/lib/utils'
import {
  X,
  ChevronLeft,
  ChevronRight,
  Download,
  ZoomIn,
  ZoomOut,
  RotateCw,
  Maximize2,
  ImageIcon,
} from 'lucide-react'

export function Lightbox() {
  const {
    lightboxImage,
    lightboxIndex,
    galleryImages,
    closeLightbox,
    nextImage,
    prevImage,
  } = useGalleryStore()

  const [zoom, setZoom] = useState(1)
  const [rotation, setRotation] = useState(0)
  const [imageError, setImageError] = useState(false)

  // Reset zoom/rotation/error when image changes
  useEffect(() => {
    setZoom(1)
    setRotation(0)
    setImageError(false)
  }, [lightboxImage?.id])

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!lightboxImage) return
      switch (e.key) {
        case 'ArrowLeft':
          prevImage()
          break
        case 'ArrowRight':
          nextImage()
          break
        case 'Escape':
          closeLightbox()
          break
        case '+':
        case '=':
          setZoom((z) => Math.min(z + 0.25, 3))
          break
        case '-':
          setZoom((z) => Math.max(z - 0.25, 0.5))
          break
        case 'r':
          setRotation((r) => (r + 90) % 360)
          break
      }
    },
    [lightboxImage, prevImage, nextImage, closeLightbox]
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const handleDownload = () => {
    if (!lightboxImage?.url) return
    const a = document.createElement('a')
    a.href = lightboxImage.url
    a.download = lightboxImage.original_filename || 'image.webp'
    a.click()
  }

  const isOpen = !!lightboxImage
  const canPrev = lightboxIndex > 0
  const canNext = lightboxIndex < galleryImages.length - 1

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && closeLightbox()}>
      <DialogContent className="max-w-[95vw] max-h-[95vh] p-0 bg-black/95 border-none overflow-hidden">
        {lightboxImage && (
          <>
            {/* Header */}
            <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between bg-gradient-to-b from-black/80 to-transparent p-4">
              <div className="text-white">
                <h3 className="font-medium">{lightboxImage.original_filename}</h3>
                <div className="flex items-center gap-2 text-sm text-white/70">
                  <span>{formatBytes(lightboxImage.file_size_bytes)}</span>
                  {lightboxImage.was_processed && (
                    <Badge variant="secondary" className="text-xs">Optimized</Badge>
                  )}
                  <span className="mx-1">|</span>
                  <span>{lightboxIndex + 1} of {galleryImages.length}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="icon" className="text-white hover:bg-white/20" onClick={() => setZoom((z) => Math.min(z + 0.25, 3))}>
                  <ZoomIn className="h-5 w-5" />
                </Button>
                <Button variant="ghost" size="icon" className="text-white hover:bg-white/20" onClick={() => setZoom((z) => Math.max(z - 0.25, 0.5))}>
                  <ZoomOut className="h-5 w-5" />
                </Button>
                <Button variant="ghost" size="icon" className="text-white hover:bg-white/20" onClick={() => setRotation((r) => (r + 90) % 360)}>
                  <RotateCw className="h-5 w-5" />
                </Button>
                <Button variant="ghost" size="icon" className="text-white hover:bg-white/20" onClick={() => setZoom(1)}>
                  <Maximize2 className="h-5 w-5" />
                </Button>
                <Button variant="ghost" size="icon" className="text-white hover:bg-white/20" onClick={handleDownload} disabled={!lightboxImage.url}>
                  <Download className="h-5 w-5" />
                </Button>
                <Button variant="ghost" size="icon" className="text-white hover:bg-white/20" onClick={closeLightbox}>
                  <X className="h-5 w-5" />
                </Button>
              </div>
            </div>

            {/* Navigation arrows */}
            {canPrev && (
              <Button
                variant="ghost"
                size="icon"
                className="absolute left-4 top-1/2 -translate-y-1/2 z-10 h-12 w-12 rounded-full bg-black/50 text-white hover:bg-black/70"
                onClick={prevImage}
              >
                <ChevronLeft className="h-8 w-8" />
              </Button>
            )}
            {canNext && (
              <Button
                variant="ghost"
                size="icon"
                className="absolute right-4 top-1/2 -translate-y-1/2 z-10 h-12 w-12 rounded-full bg-black/50 text-white hover:bg-black/70"
                onClick={nextImage}
              >
                <ChevronRight className="h-8 w-8" />
              </Button>
            )}

            {/* Image */}
            <div className="flex h-[85vh] items-center justify-center overflow-auto p-4">
              {imageError || !lightboxImage.url ? (
                <div className="flex flex-col items-center gap-4 text-white/50">
                  <ImageIcon className="h-24 w-24" />
                  <p>Image could not be loaded</p>
                </div>
              ) : (
                <img
                  src={lightboxImage.url}
                  alt={lightboxImage.original_filename}
                  className="max-h-full max-w-full object-contain transition-transform duration-200"
                  style={{
                    transform: `scale(${zoom}) rotate(${rotation}deg)`,
                  }}
                  draggable={false}
                  onError={() => setImageError(true)}
                />
              )}
            </div>

            {/* Metadata footer */}
            <div className="absolute bottom-0 left-0 right-0 z-10 bg-gradient-to-t from-black/80 to-transparent p-4">
              <div className="flex flex-wrap gap-4 text-sm text-white/80">
                {lightboxImage.project_name && (
                  <div>
                    <span className="text-white/50">Project:</span>{' '}
                    <span className="font-medium">{lightboxImage.project_name}</span>
                  </div>
                )}
                {lightboxImage.job_captain_timesheet && (
                  <div>
                    <span className="text-white/50">Job Captain:</span>{' '}
                    <span className="font-medium">{lightboxImage.job_captain_timesheet}</span>
                  </div>
                )}
                {lightboxImage.department && (
                  <div>
                    <span className="text-white/50">Department:</span>{' '}
                    <span className="font-medium">{lightboxImage.department}</span>
                  </div>
                )}
                {lightboxImage.synced_at && (
                  <div>
                    <span className="text-white/50">Synced:</span>{' '}
                    <span>{formatDate(lightboxImage.synced_at)}</span>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
