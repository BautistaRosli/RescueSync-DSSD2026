import { apiGet, apiPost } from './http'
import type { OrganizacionCreateRequest, OrganizacionRead } from '../types'

export async function listarOrganizaciones(): Promise<OrganizacionRead[]> {
  return apiGet<OrganizacionRead[]>('/organizaciones')
}

export async function crearOrganizacion(
  datos: OrganizacionCreateRequest,
): Promise<OrganizacionRead> {
  return apiPost<OrganizacionRead>('/organizaciones', datos)
}
