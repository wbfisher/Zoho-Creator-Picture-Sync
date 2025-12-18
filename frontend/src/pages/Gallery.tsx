import { useState, useCallback, useMemo } from 'react'
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { RowsPhotoAlbum } from 'react-photo-album'
import 'react-photo-album/rows.css'
import Lightbox from 'yet-another-react-lightbox'
import 'yet-another-react-lightbox/styles.css'
import Zoom from 'yet-another-react-lightbox/plugins/zoom'
import Thumbnails from 'yet-another-react-lightbox/plugins/thumbnails'
import 'yet-another-react-lightbox/plugins/thumbnails.css'

import { getImages, getFilterValues } from '@/lib/api'
import { useGalleryStore } from '@/store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { debounce } from '@/lib/utils'
import {
  Search,
  X,
  Download,
  Loader2,
  CheckSquare,
  Square,
  Image as ImageIcon,
} from 'lucide-react'
import JSZip from 'jszip'

const ITEMS_PER_PAGE = 100

export default function Gallery() {
  const { toast } = useToast()
  const [lightboxIndex, setLightboxIndex] = useState(-1)

  const {
    selectedImages,
    toggleSelection,
    selectAll,
    clearSelection,
    filters,
    setFilter,
    resetFilters,
  } = useGalleryStore()

  // Fetch filter options
  const { data: filterValues } = useQuery({
    queryKey: ['filterValues'],
    queryFn: getFilterValues,
    staleTime: 10 * 60 * 1000, // 10 minutes
  })

  // Infinite query for images
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    isError,
  } = useInfiniteQuery({
    queryKey: ['images', filters],
    queryFn: ({ pageParam = 0 }) => getImages(filters, ITEMS_PER_PAGE, pageParam),
    getNextPageParam: (lastPage, allPages) => {
      const totalFetched = allPages.reduce((sum, page) => sum + page.items.length, 0)
      return totalFetched < lastPage.total ? totalFetched : undefined
    },
    initialPageParam: 0,
  })

  // Flatten all pages into single array
  const allImages = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data?.pages]
  )
  const totalImages = data?.pages[0]?.total ?? 0

  // Convert to react-photo-album format
  const photos = useMemo(() =>
    allImages.map((img, index) => ({
      src: img.url || '',
      width: 800,  // Default aspect ratio
      height: 600,
      key: img.id,
      alt: img.original_filename || `Image ${index}`,
      // Store original data for selection/download
      _original: img,
    })),
    [allImages]
  )

  // Lightbox slides
  const slides = useMemo(() =>
    allImages.map((img) => ({
      src: img.url || '',
      alt: img.original_filename || 'Image',
    })),
    [allImages]
  )

  // Debounced search
  const debouncedSearch = useCallback(
    debounce((value: string) => setFilter('search', value || undefined), 300),
    [setFilter]
  )

  // Bulk download
  const handleBulkDownload = async () => {
    if (selectedImages.size === 0) return

    toast({ title: 'Preparing download...', description: `${selectedImages.size} images` })

    try {
      const zip = new JSZip()
      const imageIds = Array.from(selectedImages)

      for (const id of imageIds) {
        const image = allImages.find((img) => img.id === id)
        if (!image?.url) continue

        const response = await fetch(image.url)
        const blob = await response.blob()
        const filename = image.original_filename || `${id}.webp`
        zip.file(filename, blob)
      }

      const zipBlob = await zip.generateAsync({ type: 'blob' })
      const url = URL.createObjectURL(zipBlob)
      const a = document.createElement('a')
      a.href = url
      a.download = `zoho-pictures-${new Date().toISOString().split('T')[0]}.zip`
      a.click()
      URL.revokeObjectURL(url)

      toast({ title: 'Download complete', description: `${selectedImages.size} images downloaded` })
      clearSelection()
    } catch (error) {
      toast({ title: 'Download failed', description: String(error), variant: 'destructive' })
    }
  }

  const handleSelectAll = () => {
    if (selectedImages.size === allImages.length) {
      clearSelection()
    } else {
      selectAll(allImages.map((img) => img.id))
    }
  }

  // Load more when scrolling near bottom
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget
    if (scrollHeight - scrollTop <= clientHeight * 1.5 && hasNextPage && !isFetchingNextPage) {
      fetchNextPage()
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const activeFiltersCount = Object.values(filters).filter(Boolean).length

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col gap-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search images..."
            className="pl-9"
            onChange={(e) => debouncedSearch(e.target.value)}
          />
        </div>

        {/* Filters */}
        <Select
          value={filters.job_captain_timesheet || '__all__'}
          onValueChange={(val) => setFilter('job_captain_timesheet', val === '__all__' ? undefined : val)}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Job Captain Timesheet" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Timesheets</SelectItem>
            {filterValues?.job_captain_timesheets.map((jc) => (
              <SelectItem key={jc} value={jc}>{jc}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.project_name || '__all__'}
          onValueChange={(val) => setFilter('project_name', val === '__all__' ? undefined : val)}
        >
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Project" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Projects</SelectItem>
            {filterValues?.project_names.map((proj) => (
              <SelectItem key={proj} value={proj}>{proj}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.department || '__all__'}
          onValueChange={(val) => setFilter('department', val === '__all__' ? undefined : val)}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Department" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Departments</SelectItem>
            {filterValues?.departments.map((dept) => (
              <SelectItem key={dept} value={dept}>{dept}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.photo_origin || '__all__'}
          onValueChange={(val) => setFilter('photo_origin', val === '__all__' ? undefined : val)}
        >
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Photo Origin" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All Origins</SelectItem>
            {filterValues?.photo_origins?.map((origin) => (
              <SelectItem key={origin} value={origin}>{origin}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {activeFiltersCount > 0 && (
          <Button variant="ghost" size="sm" onClick={resetFilters}>
            <X className="mr-1 h-4 w-4" />
            Clear ({activeFiltersCount})
          </Button>
        )}
      </div>

      {/* Selection toolbar */}
      <div className="flex items-center justify-between border-b pb-3">
        <div className="flex items-center gap-4">
          <Button variant="outline" size="sm" onClick={handleSelectAll}>
            {selectedImages.size === allImages.length && allImages.length > 0 ? (
              <CheckSquare className="mr-2 h-4 w-4" />
            ) : (
              <Square className="mr-2 h-4 w-4" />
            )}
            {selectedImages.size > 0 ? `${selectedImages.size} selected` : 'Select All'}
          </Button>

          {selectedImages.size > 0 && (
            <>
              <Button variant="outline" size="sm" onClick={handleBulkDownload}>
                <Download className="mr-2 h-4 w-4" />
                Download ZIP
              </Button>
              <Button variant="ghost" size="sm" onClick={clearSelection}>
                Clear Selection
              </Button>
            </>
          )}
        </div>

        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <ImageIcon className="h-4 w-4" />
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <span>{totalImages.toLocaleString()} images</span>
          )}
        </div>
      </div>

      {/* Photo Gallery */}
      <div
        className="flex-1 overflow-auto rounded-lg border bg-muted/30 p-2"
        onScroll={handleScroll}
      >
        {isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : isError ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            Failed to load images
          </div>
        ) : allImages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <ImageIcon className="h-12 w-12" />
            <p>No images found</p>
            {activeFiltersCount > 0 && (
              <Button variant="link" size="sm" onClick={resetFilters}>
                Clear filters
              </Button>
            )}
          </div>
        ) : (
          <>
            <RowsPhotoAlbum
              photos={photos}
              targetRowHeight={200}
              rowConstraints={{ minPhotos: 3, maxPhotos: 8 }}
              spacing={8}
              onClick={({ index }) => setLightboxIndex(index)}
              render={{
                image: (props, context) => {
                  const originalImage = (context.photo as typeof photos[0])._original
                  const isSelected = selectedImages.has(originalImage.id)
                  return (
                    <div
                      className={`relative group cursor-pointer ${isSelected ? 'ring-2 ring-primary ring-offset-2' : ''}`}
                      onClick={(e) => {
                        if (e.shiftKey || e.ctrlKey || e.metaKey) {
                          e.stopPropagation()
                          toggleSelection(originalImage.id)
                        }
                      }}
                    >
                      <img
                        {...props}
                        className="rounded-md transition-transform group-hover:scale-[1.02]"
                      />
                      {/* Selection indicator */}
                      <div
                        className={`absolute top-2 left-2 w-5 h-5 rounded border-2 flex items-center justify-center transition-opacity ${
                          isSelected
                            ? 'bg-primary border-primary opacity-100'
                            : 'bg-black/50 border-white opacity-0 group-hover:opacity-100'
                        }`}
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleSelection(originalImage.id)
                        }}
                      >
                        {isSelected && (
                          <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        )}
                      </div>
                    </div>
                  )
                }
              }}
            />
            {isFetchingNextPage && (
              <div className="flex justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            )}
            {!hasNextPage && allImages.length > 0 && (
              <p className="text-center py-4 text-sm text-muted-foreground">
                All {totalImages.toLocaleString()} images loaded
              </p>
            )}
          </>
        )}
      </div>

      {/* Lightbox */}
      <Lightbox
        open={lightboxIndex >= 0}
        close={() => setLightboxIndex(-1)}
        index={lightboxIndex}
        slides={slides}
        plugins={[Zoom, Thumbnails]}
        carousel={{ finite: false }}
        zoom={{ maxZoomPixelRatio: 3 }}
        thumbnails={{ position: 'bottom', width: 100, height: 60 }}
      />
    </div>
  )
}
