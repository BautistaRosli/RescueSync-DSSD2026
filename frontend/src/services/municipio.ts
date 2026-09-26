import { apiGet } from './http'
import type { MunicipioRead } from '../types'

export async function listarMunicipios(): Promise<MunicipioRead[]> {
  return apiGet<MunicipioRead[]>('/municipios')
}
