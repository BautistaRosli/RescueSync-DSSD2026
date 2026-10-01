import { apiGet } from './http'
import type { Organizacion } from '../types'

export async function listarOrganizaciones(): Promise<Organizacion[]> {
  return apiGet<Organizacion[]>('/organizaciones')
}
