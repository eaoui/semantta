import { useDisplay } from './useDisplay'

/**
 * Public display variant – always formats URIs in "label" mode.
 */
export const usePublicDisplay = () => {
  const { formatUri } = useDisplay()

  const publicFormatUri = (uri: string): string => {
    return formatUri(uri, 'label')
  }

  return { formatUri: publicFormatUri }
}