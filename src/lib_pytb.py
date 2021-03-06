from __future__ import print_function
from __future__ import division
from scipy import linalg as sla
from functools import partial
import multiprocessing
import numpy as np
import xml.etree.ElementTree as ET
import numpy.linalg as la
import sys
import re
import os
import time
import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import lib_utils as utils
import lib_misc_utils as mutils



Ry2eV   = 13.60569193
Ha2eV   = 2*Ry2eV

def build_HR_3(ineigh,neigh_indx_3d,nkpnts,kpnts,kpnts_wght,alat,a_vectors,nawf,ispin,Hk,Sk):
    
    if Sk is None:
        is_wannier=True
    else:
        is_wannier=False

    H = np.zeros((nawf,nawf),dtype=np.complex_)
    if not is_wannier:
        S = np.zeros((nawf,nawf),dtype=np.complex_)

    R = np.dot(neigh_indx_3d[ineigh],a_vectors)

    for ik in range(nkpnts):
        K = 2*np.pi/alat*kpnts[ik,:]
        H = H + kpnts_wght[ik]*np.exp(-1j*np.dot(K,R))*Hk[:,:,ik,ispin]
        if not is_wannier:
            S = S + kpnts_wght[ik]*np.exp(-1j*np.dot(K,R))*Sk[:,:,ik]

    H = H/np.sum(kpnts_wght)
    if is_wannier: 
        S = None 
    else:
        S = S/np.sum(kpnts_wght)

    return H,S
def build_HR_par_6(QE_xml_data_file,HR_file,Hk_file,Hk_space,
                   WS_supercell_file='',nx=0,ny=0,nz=0,nproc=1):
    

    from multiprocessing import Pool
    fname = utils.fname() 
    HR_file_dir =  os.path.dirname(HR_file) 
    if not os.path.isdir(HR_file_dir): 
       print('{0:s}: Directory {1:s} does not exist. Attempting to create it'.format(fname,HR_file_dir) ) 
       os.makedirs(HR_file_dir)
    if not os.path.isfile(QE_xml_data_file):
        sys.exit('{0:s}: QE_xml_data_file does not exist.'.format(fname) )
    if not os.path.isfile(Hk_file): 
        sys.exit('{0:s}: Hk_file/Uk_file does not exist.'.format(fname) )

    if (not WS_supercell_file) and (nx*ny*nz == 0): 
        sys.exit('{0:s}: Wrong values for nx,ny,nz'.format(fname) )
    
    data      = np.load(QE_xml_data_file)
    alat      = data['alat']
    a_vectors = data['a_vectors']
    nkpnts    = int(data['nkpnts'])
    nspin     = int(data['nspin'])
    kpnts     = data['kpnts']
    kpnts_wght= data['kpnts_wght']
   
    Hk_space = Hk_space.lower()

    if Hk_space == 'wannier':
        Efermi = data['Efermi']  #in eV
        is_wannier = True
        Sk = None
        
        uk = np.load(Hk_file)
        nkpnts,nbandswann,nwann = uk.shape

        eigs_infile = os.path.join( os.path.dirname(Hk_file) ,'eig.npy' )
        if not os.path.isfile(eigs_infile): sys.exit('file {0:s} not found'.format(eigs_infile))

        if kpnts.shape[0] != nkpnts: sys.error('Inconsistent number of kpoints')
        nawf = nwann


        Ek_aux = np.load(eigs_infile) #nkpnts, nbandswann
        nkpnts_,nbandswann_ = Ek_aux.shape

        if (nbandswann_ != nbandswann) or (nkpnts_ != nkpnts) :
            sys.exit('Inconsistent number of nbands or nkpnts ') 
        Hk = np.zeros((nwann,nwann,nkpnts,nspin),dtype=complex)
        if nspin > 1: sys.exit('nspin > 1 not implemented')
        ispin = 0
        for ik in range(nkpnts):
            Uk = np.asmatrix(uk[ik,:,:])  #nbandswann x nwann
            Ek = np.asmatrix(np.diag(Ek_aux[ik,:]))
            Hk[:,:,ik,ispin] = Uk.H*Ek*Uk 
    elif (Hk_space == 'ortho') or (Hk_space == 'nonortho'):
        nawf_      = int(data['nawf'])
        is_wannier = False
        Hk = np.load(Hk_file)['Hk']
        nawf    = Hk.shape[0]
        if nawf != nawf_:
            print('WARNING!!, mismatch nawf in xml is {0:d}, while nawf in Hk is {1:d}'.format(nawf_,nawf))
        Sk = data['Sk']
    else:
       sys.exit('{0:s}: Value of Hk_space not recognized'.format(fname))

    del data

    pool      = multiprocessing.Pool(processes = nproc)


  
    if not WS_supercell_file:
        w_Re,irvec_Re   = get_WS_supercell(nx,ny,nz,a_vectors)
        cell_type       = 'wigner-seitz'
    else:
        print('This is WS_supercell_file: ', WS_supercell_file)
        sys.exit('Deprecating this option. It tended to mix up data')
        aux       = np.load(WS_supercell_file)
        irvec_Re  = aux['irvec']
        w_Re      = 1.0/aux['ndegen_Re']
        cell_type = str(aux['cell_type'])

    nneighs   = len(irvec_Re)

    if is_wannier:
        nmatrices = 1
    else:
        nmatrices = 2

    HR_mat = np.zeros((nspin,nneighs,nmatrices,nawf,nawf),dtype=np.complex_)

    for ispin in range(nspin):
        tic = time.time()
        partial_build_HR= partial(build_HR_3,neigh_indx_3d=irvec_Re, \
                                  nkpnts=nkpnts,kpnts=kpnts,kpnts_wght=kpnts_wght, \
                                  alat=alat,a_vectors=a_vectors,nawf=nawf, \
                                  ispin=ispin,Hk=Hk,Sk=Sk)

        aux = pool.map(partial_build_HR,xrange(nneighs))
  
        pool.close()
        pool.join()
  

        for ir in range(nneighs):
            Haux,Saux = aux[ir]
            HR_mat[ispin,ir,0,:,:] = Haux
            if not is_wannier: 
                HR_mat[ispin,ir,1,:,:] = Saux

        toc = time.time()
        hours, rem = divmod(toc-tic, 3600)
        minutes, seconds = divmod(rem, 60)
        print("{0:s}: Parallel processing of H[R] with {1:d} processors".format(fname,nproc))
        print("{0:s}: Elapsed time {1:02d}:{2:02d}:{3:5.2f}".format(fname,int(hours),int(minutes),seconds))

    np.savez(HR_file,HR_mat=HR_mat,irvec_Re=irvec_Re,cell_type=cell_type,Hk_space=Hk_space,\
             w_Re=w_Re,alat=alat,a_vectors=a_vectors,nspin=nspin, nRe = len(w_Re), nibnds = nawf)

    print('{0:s}: Saving data in {1:s}'.format(fname,HR_file))
    return HR_mat,irvec_Re,w_Re
def get_WS_supercell(nk1,nk2,nk3,a_vectors):
    startt = time.time()
    nrpts = 0
    eps7  = 1e-7
    ndegen= []
    irvec = []
    dist = np.zeros(125)
    for n1 in range(-2*nk1,2*nk1+1):
        for n2 in range(-2*nk2,2*nk2+1): 
            for n3 in range(-2*nk3,2*nk3+1):
                icnt = 0
                for i1 in range(-2,2+1): 
                    for i2 in range(-2,2+1): 
                        for i3 in range(-2,2+1):
                            ndiff     = [n1-i1*nk1,n2-i2*nk2,n3-i3*nk3]
                            dist[icnt]= la.norm(np.dot(ndiff,a_vectors))**2
                            icnt      = icnt + 1
                dist_min = np.min(dist)               
                if  np.abs(dist[62]-dist_min ) < eps7:
                    nrpts = nrpts + 1
                    ndegen = ndegen + [len((np.where(np.abs(dist-dist_min)<eps7))[0])]
                    irvec  = irvec + [[n1,n2,n3]]
    if len(irvec) != nrpts: 
        print(len(irvec),nrpts)
        sys.exit('wrong dimensions')
    
    tot = np.sum( 1/np.array(ndegen))
    if (np.abs(tot - nk1*nk2*nk3) > eps7) : 
       print(tot)
       sys.exit('Missing some points in W-S cell')

    endt = time.time()
    elapsed1 = str(datetime.timedelta(seconds=(endt - startt)))
    print("get_WS_supercell: elapsed time  {0:s}".format(elapsed1))
    return 1/np.array(ndegen),np.array(irvec)
def linspace_vector_2(v1,v2,ndivs):
    lx = np.reshape(np.linspace(v1[0],v2[0],ndivs),(ndivs,1))
    ly = np.reshape(np.linspace(v1[1],v2[1],ndivs),(ndivs,1))
    lz = np.reshape(np.linspace(v1[2],v2[2],ndivs),(ndivs,1))
    return np.hstack((lx,ly,lz))
def create_kpaths_2(nkmesh,K):
    
    sys.exit('Deprecated: use PyTB/src/lib_utils.create_kpaths instead or Perturbo/src/lib_utils.create_kpaths (both must be equal)')
    nKpoints = len(K)
    if len(nkmesh) != nKpoints-1: sys.exit('size of nkmesh does not agree with number of kpaths')
    list_aux = []
    for ipath in range(nKpoints-1):
        K1  = K[ipath]
        K2  = K[ipath+1]
        npoints = nkmesh[ipath] if ipath == 0 else nkmesh[ipath]+1
        lvec= linspace_vector_2(K1,K2,npoints)
        if ipath < nKpoints-1-1:
            lvec = lvec[:-1,:]
        list_aux = list_aux + lvec.tolist()
    return list_aux
def get_interpolated_bands_3(Kfrac,nkmesh,HR_mat_path,fig_erange=[-20,10]):
    """
    get_interpolated_bands_3, changes the variable neigh_indx_3d for irvec
    get_interpolated_bands_2: Does not use nx,ny,nz. Loads the real-space grid from HR_mat
    """
    aux=np.load(HR_mat_path)
    HR_mat        = aux['HR_mat']
    irvec         = aux['irvec_Re']
    cell_type     = str(aux['cell_type'])
    Hk_space      = str(aux['Hk_space'])
    w_Re          = aux['w_Re']
    a_vectors     = aux['a_vectors']
    alat          = aux['alat']
    nspin         = aux['nspin']
    
    nawf          = HR_mat.shape[3]



    B          = 2*np.pi*la.inv(np.transpose(a_vectors))
    Kfrac_list = np.dot(np.array(Kfrac),B).tolist()
    Kpath,_    = utils.create_kpaths(nkmesh,Kfrac_list)
    nkpath     = len(Kpath)
    nneighs    = len(irvec)
    Rarray     = np.dot(irvec,a_vectors) #a_vectors are in Bohrs
    Ek         = np.zeros((nawf,nkpath,nspin))

    nmatrices  = HR_mat.shape[2]
    Hk_space = Hk_space.lower()

    if (Hk_space == 'ortho') or (Hk_space == 'wannier'):
        nonortho_space= False
    elif Hk_space == 'nonortho':
        nonortho_space= True
    else:
        sys.exit('get_interpolated_bands_3: wrong Hk_space')

         

    for ik in range(nkpath):
        for ispin in range(nspin):
            Hk = np.zeros((nawf,nawf),dtype=complex)
            if nonortho_space: Sk = np.zeros((nawf,nawf),dtype=complex)
            for ineigh in range(nneighs):
                H = HR_mat[ispin,ineigh,0,:,:]
                if nonortho_space:
                    S = HR_mat[ispin,ineigh,1,:,:]
                K   = Kpath[ik]      #K in 1/Bohrs
                R   = Rarray[ineigh,:]
                
                
                Hk  = Hk + w_Re[ineigh]*H*np.exp(+1j*np.dot(K,R))
                if nonortho_space: Sk  = Sk + w_Re[ineigh]*S*np.exp(+1j*np.dot(K,R))

            Hk_hermitian = np.triu(Hk,1)+np.diag(np.diag(Hk))+np.conj(np.triu(Hk,1)).T

            if nonortho_space:
                Sk_hermitian = np.triu(Sk,1)+np.diag(np.diag(Sk))+np.conj(np.triu(Sk,1)).T
            
                is_positive = np.all(la.eigvalsh(Sk_hermitian) > 0)
                if not is_positive:
                    print("Sk_hermitian not positive definite at ik = {0:2d}".format(ik))

            if nonortho_space:
                eigval, _ = sla.eig(Hk_hermitian,Sk_hermitian)
            else:
                eigval = sla.eigvalsh(Hk_hermitian)

            Ek[:,ik,ispin] = np.sort(np.real(eigval))

    Kpath1 = np.array(Kpath)/(2*np.pi/alat)
    output_dir = os.path.dirname(HR_mat_path)
    band_plot_2(output_dir,Kpath1,Ek,cell_type,Hk_space,fig_erange)

    return
def band_plot_2(fpath,Kpath1,Ek,cell_type,Hk_space,erange=[-20,10]):
    
    nkpnts = Ek.shape[1]
    nbnds  = Ek.shape[0]
    nspin  = Ek.shape[2]

    if cell_type.lower() == 'wigner-seitz':
       cell_type_label = 'ws'
    else:
       cell_type_label = cell_type.lower()

    for ispin in range(nspin):
        if nspin==1:
            suffix=''
        else:
            if ispin == 1:
                suffix='_up'
            elif ispin == 2:
                suffix='_dn'
            else:
                sys.exit('ispin case not contemplated')
    datafile = os.path.join(fpath, 'bands'+suffix+'_'+Hk_space+'_'+cell_type_label+'.txt')
    fid = open(datafile , 'w')
    for ibnd in range(nbnds):
        dk = 0.0
        for ik in range(nkpnts):
            if ik==0: k0=Kpath1[ik,:]
            a  = Kpath1[ik,:] - k0
            dk = dk + la.norm(a)
            print('{0:f} {1:f}'.format(dk,Ek[ibnd,ik,ispin]),file=fid)
            k0 = Kpath1[ik,:]
        print(' ',file=fid)
    fid.close()

    bands = mutils.read_gnuplot_data(datafile,sep_str='\n \n')
    nbnds = len(bands)
    fig=plt.figure()
    for i in range(nbnds):
          x = bands[i][:,0]
          y = bands[i][:,1]
          plt.plot(range(len(x)),y,'.-',linewidth=0.1)

    plt.xlabel('k-points')
    plt.ylabel('Energy - E$_F$ (eV)')
    plt.ylim(erange[0],erange[1])

    plt.gca().grid(True)
    pdffile = os.path.splitext(datafile)[0]+'.pdf'
    print('band_plot_2: A figure has been saved to {0:s}'.format(pdffile))
    plt.savefig(pdffile,format='pdf')
    return
def build_Hk_5(QE_xml_data_file,shift,shift_type,Hk_space,Hk_outfile,nbnds_norm=0,nbnds_in=0):
    """
    returns Hk:
    build_Hk_2: includes all the bands that lay under the 'shift' energy.
    build_Hk_3: Optionally one can inclue a fixed number of bands with 'nbnds_in';
                this capability is similar to WanT's 'atmproj_nbnd'.
    shift_type: 0 = regular shifting. 1 = new shifting

    build_Hk_4: -a bug for nonortho shifting is corrected: Sks was needed for that case.
                -changed the name of the output variable from Hks to Hk.
    build_Hk_5: reads nawf,nkpnts,nspin,shift,eigsmat, from QE_xml_data_file
    """
    nproc = 1

    if not os.path.isfile(QE_xml_data_file):
        sys.exit('File not found: {0:s}'.format(QE_xml_data_file))
    data      = np.load(QE_xml_data_file)
    nawf      = int(data['nawf'])
    nkpnts    = int(data['nkpnts'])
    nspin     = int(data['nspin'])
    eigsmat   = data['eigsmat']
    Sks       = data['Sk']
    U         = data['U']


    if Hk_space.lower()=='ortho':
       del Sks 
    elif Hk_space.lower()=='nonortho':
       if len(Sks.shape) != 3: sys.exit('Need Sks[nawf,nawf,nkpnts]  for nonortho calculations')
    else:
       sys.exit('wrong Hk_space option. Only ortho and nonortho are accepted')

    tic = time.time()
    Hks = np.zeros((nawf,nawf,nkpnts,nspin),dtype=complex)
    for ispin in range(nspin):
        for ik in range(nkpnts):
            my_eigs=eigsmat[:,ik,ispin]
            E = np.diag(my_eigs)
            UU    = U[:,:,ik,ispin] #transpose of U. Now the columns of UU are the eigenvector of length nawf
            if nbnds_norm > 0:
                norms = 1/np.sqrt(np.real(np.sum(np.conj(UU)*UU,axis=0)))
                UU[:,:nbnds_norm] = UU[:,:nbnds_norm]*norms[:nbnds_norm]
            kappa = shift
            if nbnds_in == 0:
               iselect   = np.where(my_eigs <= shift)[0]
            elif nbnds_in > 0:
               iselect   = range(nbnds_in)
            else:
               sys.exit('build_Hk_4: wrong nbnd variable')

            ac    = UU[:,iselect]
            ee1   = E[np.ix_(iselect,iselect)]

            if shift_type ==0:
                Hks_aux = ac.dot(ee1).dot(np.conj(ac).T) + kappa*( -ac.dot(np.conj(ac).T))
            elif shift_type==1:
                aux_p=la.inv(np.dot(np.conj(ac).T,ac))
                Hks_aux = ac.dot(ee1).dot(np.conj(ac).T) + kappa*( -ac.dot(aux_p).dot(np.conj(ac).T))
            else:
                sys.exit('shift_type not recognized')


                Hks_aux = np.triu(Hks_aux,1)+np.diag(np.diag(Hks_aux))+np.conj(np.triu(Hks_aux,1)).T

            if Hk_space.lower()=='ortho':
                Hks[:,:,ik,ispin] = Hks_aux  + kappa*np.identity(nawf)
            elif Hk_space.lower()=='nonortho':
                Sk_half = sla.fractional_matrix_power(Sks[:,:,ik],0.5)
                if 'multi_dot' in dir (la):
                    Hks[:,:,ik,ispin] =la.multi_dot([Sk_half,Hks_aux,Sk_half])+kappa*Sks[:,:,ik]
                else:
                    Hks[:,:,ik,ispin] =np.dot(np.dot(Sk_half,Hks_aux),Sk_half)+kappa*Sks[:,:,ik]

            else:
                sys.exit('wrong Hk_space option. Only ortho and nonortho are accepted')


    
    np.savez(Hk_outfile,Hk=Hks,nbnds_norm=nbnds_norm,nbnds_in=nbnds_in,shift_type=shift_type,shift=shift)
            
    toc = time.time()
    hours, rem = divmod(toc-tic, 3600)
    minutes, seconds = divmod(rem, 60)
    print("Parallel calculation of H[k] with {0:d} processors".format(nproc))
    print("Elapsed time {:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds))
    return Hks
def read_eigenvalues_xml_par(nkpnts,Efermi,nspin,ispin,root,nproc):
    from multiprocessing import Pool
    pool       = multiprocessing.Pool(processes = nproc)
    partial_read_eigenvalues = partial(read_eigenvalues_xml,Efermi=Efermi,nspin=nspin,ispin=ispin,root=root)
    my_eigsmat = pool.map(partial_read_eigenvalues,xrange(nkpnts))
    pool.close()
    pool.join()
    return my_eigsmat
def read_projections_xml_par(nkpnts,nawf,nbnds,nspin,ispin,root,nproc):
    from multiprocessing import Pool
    pool       = multiprocessing.Pool(processes = nproc)
    partial_read_projections= partial(read_projections_xml,nawf=nawf,nbnds=nbnds,nspin=nspin,ispin=ispin,root=root)
    Uaux = pool.map(partial_read_projections,xrange(nkpnts))
    pool.close()
    pool.join()
    return Uaux
def read_overlap_xml_par(nkpnts,nawf,root,nproc):
    from multiprocessing import Pool
    pool       = multiprocessing.Pool(processes = nproc)
    partial_read_overlap = partial(read_overlap_xml,nawf=nawf,root=root)
    Sks = pool.map(partial_read_overlap,xrange(nkpnts))
    pool.close()
    pool.join()
    return Sks
def read_QE_data_file_xml_v2(data_file,data_file_out=''):
    fname = utils.fname() 
   
    if not os.path.isfile(data_file):
        sys.exit('{0:s}: File {1:s} does not exist'.format(fname,data_file))
   
    print('{0:s}: Reading data-file.xml ...'.format(fname))
    tree  = ET.parse(data_file)
    root  = tree.getroot()
   
    alat_units  = root.findall("./CELL/LATTICE_PARAMETER")[0].attrib['UNITS']
    alat   = float(root.findall("./CELL/LATTICE_PARAMETER")[0].text.split()[0])
   
   
    a_vectors_units  = root.findall("./CELL/DIRECT_LATTICE_VECTORS/UNITS_FOR_DIRECT_LATTICE_VECTORS")[0].attrib['UNITS']
    aux=root.findall("./CELL/DIRECT_LATTICE_VECTORS/a1")[0].text.split()
    a1=[float(i) for i in aux]
   
    aux=root.findall("./CELL/DIRECT_LATTICE_VECTORS/a2")[0].text.split()
    a2=[float(i) for i in aux]
   
    aux=root.findall("./CELL/DIRECT_LATTICE_VECTORS/a3")[0].text.split()
    a3=[float(i) for i in aux]
   
    a_vectors = np.array([a1,a2,a3]) #in Bohrs
    print('{0:s}: Direct lattice vectors ({1:s}):'.format(fname,a_vectors_units))
    print(a_vectors)
   
    b_vectors_units   =root.findall("./CELL/RECIPROCAL_LATTICE_VECTORS/UNITS_FOR_RECIPROCAL_LATTICE_VECTORS")[0]
    aux=root.findall("./CELL/RECIPROCAL_LATTICE_VECTORS/b1")[0].text.split()
    b1=[float(i) for i in aux]
   
    aux=root.findall("./CELL/RECIPROCAL_LATTICE_VECTORS/b2")[0].text.split()
    b2=[float(i) for i in aux]
   
    aux=root.findall("./CELL/RECIPROCAL_LATTICE_VECTORS/b3")[0].text.split()
    b3=[float(i) for i in aux]
   
    b_vectors = np.array([b1,b2,b3]) #in Bohrs
   

    nspin=  int (root.findall("./BAND_STRUCTURE_INFO/NUMBER_OF_SPIN_COMPONENTS")[0].text.strip() )
    nbnds=  int (root.findall("./BAND_STRUCTURE_INFO/NUMBER_OF_BANDS")[0].text.strip() )
    Efermi= float(root.findall("./BAND_STRUCTURE_INFO/FERMI_ENERGY")[0].text.strip() )
    Efermi_units= root.findall("./BAND_STRUCTURE_INFO/UNITS_FOR_ENERGIES")[0].attrib['UNITS']
    if Efermi_units=='Hartree':
       Efermi_units='eV'
       Efermi = Efermi*Ha2eV
    else:
       sys.error('Energy units has to be in Hartree')


    nkpnts  = int(root.findall("./BRILLOUIN_ZONE/NUMBER_OF_K-POINTS")[0].text.strip())
    kpnts   = np.zeros((nkpnts,3))
    weights = np.zeros(nkpnts)
    for ik in range(nkpnts):
        weights[ik] = float(root.findall("./BRILLOUIN_ZONE/K-POINT.{0:d}".format(ik+1))[0].attrib['WEIGHT'])
        aux         = root.findall("./BRILLOUIN_ZONE/K-POINT.{0:d}".format(ik+1))[0].attrib['XYZ']
        kpnts[ik,:] = np.array([float(i) for i in aux.split()])
  
    nsym     = int(root.findall("./SYMMETRIES/NUMBER_OF_SYMMETRIES")[0].text.split()[0])
    nrot     = int(root.findall("./SYMMETRIES/NUMBER_OF_BRAVAIS_SYMMETRIES")[0].text.split()[0])
    aux      = root.findall("./SYMMETRIES/INVERSION_SYMMETRY")[0].text.split()[0]
    invsym   = aux in ['T'] #QE output
    aux      = root.findall("./SYMMETRIES/DO_NOT_USE_TIME_REVERSAL")[0].text.split()[0]
    noinv    = aux in ['T'] #QE input
    aux      = root.findall("./SYMMETRIES/TIME_REVERSAL_FLAG")[0].text.split()[0]
    time_reversal = aux in ['T'] #QE output
    units_for_symmetries = root.findall("./SYMMETRIES/UNITS_FOR_SYMMETRIES")[0].attrib['UNITS']
    aux      = root.findall("./SYMMETRIES/NO_TIME_REV_OPERATIONS")[0].text.split()[0]
    no_t_rev = aux in ['T'] #QE input
    symop    = np.zeros((nrot,3,3), dtype=np.int)

    units_for_symmetries = root.findall("./SYMMETRIES/UNITS_FOR_SYMMETRIES")[0].attrib['UNITS']

    for irot in range(nrot):
        aux = root.findall("./SYMMETRIES/SYMM.{0:d}/ROTATION".format(irot+1))[0].text
        symop[irot, ... ] = np.transpose(np.reshape(np.fromstring(aux,dtype='int',sep='\n'),(3,3)))

    natoms  = int(root.findall("./IONS/NUMBER_OF_ATOMS")[0].text.split()[0])
    ntype   = int(root.findall("./IONS/NUMBER_OF_SPECIES")[0].text.split()[0])
    psp_dir= root.findall("./IONS/PSEUDO_DIR")[0].text.split()[0]
   
    itype = ['None']*ntype
    ipsp  = ['None']*ntype
   
    atoms_units = root.findall("./IONS/UNITS_FOR_ATOMIC_POSITIONS")[0].attrib['UNITS']
    for i in range(ntype):
        flabel= "./IONS/SPECIE.{0:d}/ATOM_TYPE".format(i+1)
        itype[i]= root.findall(flabel)[0].text.split()[0]
        flabel= "./IONS/SPECIE.{0:d}/PSEUDO".format(i+1)
        ipsp[i] = os.path.join(psp_dir,root.findall(flabel)[0].text.split()[0])
   
    atoms_species = ['None']*natoms
    atoms_index   = ['None']*natoms
    atoms_coords  = np.zeros((natoms,3))
    for i in range(natoms):
        flabel= "./IONS/ATOM.{0:d}".format(i+1)
        atoms_species[i]= root.findall(flabel)[0].attrib['SPECIES'].split()[0]
        atoms_index[i]  = int(root.findall(flabel)[0].attrib['INDEX'])
        atoms_coords[i,:]  = np.array(map(float,root.findall(flabel)[0].attrib['tau'].split()))
   
   
    nr1 = int(root.findall("./PLANE_WAVES/FFT_GRID")[0].attrib['nr1'])
    nr2 = int(root.findall("./PLANE_WAVES/FFT_GRID")[0].attrib['nr2'])
    nr3 = int(root.findall("./PLANE_WAVES/FFT_GRID")[0].attrib['nr3'])
   
    if data_file_out != '':
        print('{0:s}: Saving data-file.xml data to file {1:s}'.format(fname,data_file_out))
        np.savez(data_file_out, 
                 alat_units=alat_units,\
                 alat=alat,\
                 a_vectors=a_vectors,\
                 a_vectors_units=a_vectors_units,\
                 b_vectors=b_vectors,\
                 b_vectors_units=b_vectors_units,\
                 kpnts=kpnts,\
                 weights=weights,\
                 itype=itype,\
                 ipsp=ipsp,\
                 atoms_units=atoms_units,\
                 atoms_species=atoms_species,\
                 atoms_index=atoms_index,\
                 atoms_coords=atoms_coords,\
                 nr1=nr1, nr2=nr2, nr3=nr3,\
                 Efermi=Efermi, Efermi_units=Efermi_units,\
                 nbnds=nbnds,nkpnts=nkpnts,kpnts_wght=weights,nspin=nspin,\
                 nrot=nrot, nsym=nsym, invsym=invsym, symop=symop) #sym
   
    return  {'alat_units':alat_units,\
             'alat':alat,\
             'a_vectors':a_vectors,\
             'a_vectors_units':a_vectors_units,\
             'b_vectors':b_vectors,\
             'b_vectors_units':b_vectors_units,\
             'kpnts':kpnts,\
             'weights':weights,\
             'itype':itype,\
             'ipsp':ipsp,\
             'atoms_units':atoms_units,\
             'atoms_species':atoms_species,\
             'atoms_index':atoms_index,\
             'atoms_coords':atoms_coords,\
             'nr1':nr1, 'nr2':nr2, 'nr3':nr3,\
             'Efermi':Efermi, 'Efermi_units':Efermi_units,\
             'nbnds':nbnds, 'nkpnts':nkpnts, 'kpnts_wght':weights, 'nspin':nspin,\
             'nrot':nrot, 'nsym':nsym, 'invsym':invsym, 'symop':symop} #sym
def read_QE_output_xml_v4(data_file,QE_xml_data_file,atomic_proj='',read_eigs=True, read_U=False, read_S=False, nproc=1):
    

    fname = utils.fname() 
   
    if atomic_proj :
        read_atomic_proj = True
    else:
        read_atomic_proj = False

        
    if not os.path.isfile(data_file):
        sys.exit('{0:s}: File {1:s} does not exist'.format(fname,data_file))

    if read_atomic_proj and (not os.path.isfile(atomic_proj)):
        sys.exit('{0:s}: File {1:s} does not exist'.format(fname,atomic_proj))
   
    QE_xml_data_dir = os.path.dirname(QE_xml_data_file)
    if not os.path.isdir(QE_xml_data_dir):
        print('{0:s}: Ouput directory {1:s} does not exist.'
              ' Attempting to create it.'.format(fname,QE_xml_data_dir))
        os.makedirs(QE_xml_data_dir)
   
    aux         = read_QE_data_file_xml_v2(data_file)
    alat_units  = aux['alat_units']
    alat        = aux['alat']
    a_vectors_units   = aux['a_vectors_units']
    a_vectors   = aux['a_vectors']
    nrot        = aux['nrot']   #sym
    nsym        = aux['nsym']   
    invsym      = aux['invsym'] 
    symop       = aux['symop'] 

    if not read_atomic_proj: 
        kpnts      = aux['kpnts']
        kpnts_wght = aux['weights']
        nkpnts     = int(aux['nkpnts'])
        nspin      = int(aux['nspin'])
        nbnds      = int(aux['nbnds'])
        Efermi     = float(aux['Efermi'])
        Efermi_units= aux['Efermi_units']
        nawf       = 0
        np.savez(QE_xml_data_file, nawf=nawf, \
                 alat_units=alat_units, alat=alat, a_vectors_units=a_vectors_units, a_vectors=a_vectors, \
                 nkpnts=nkpnts, nspin=nspin, kpnts=kpnts, kpnts_wght=kpnts_wght, \
                 nbnds=nbnds, Efermi=Efermi, Efermi_units=Efermi_units,\
                 nrot=nrot, nsym=nsym, invsym=invsym, symop=symop)
        return


    print('Reading atomic_proj.xml ...')
    tree  = ET.parse(atomic_proj)
    root  = tree.getroot()
   
    nkpnts = int(root.findall("./HEADER/NUMBER_OF_K-POINTS")[0].text.strip())
    print('Number of kpoints: {0:d}'.format(nkpnts))
   
    nspin  = int(root.findall("./HEADER/NUMBER_OF_SPIN_COMPONENTS")[0].text.split()[0])
    print('Number of spin components: {0:d}'.format(nspin))
   
    kunits = root.findall("./HEADER/UNITS_FOR_K-POINTS")[0].attrib['UNITS']
    print('Units for the kpoints: {0:s}'.format(kunits))
   
    aux = root.findall("./K-POINTS")[0].text.split()
    kpnts  = np.array([float(i) for i in aux]).reshape((nkpnts,3))
    print('Read the kpoints')
   
    aux = root.findall("./WEIGHT_OF_K-POINTS")[0].text.split()
    kpnts_wght  = np.array([float(i) for i in aux])
   
    if kpnts_wght.shape[0] != nkpnts:
    	sys.exit('Error in size of the kpnts_wght vector')
    else:
    	print('Read the weight of the kpoints')
   
   
    nbnds  = int(root.findall("./HEADER/NUMBER_OF_BANDS")[0].text.split()[0])
    print('Number of bands: {0:d}'.format(nbnds))
   
    Efermi_units    = root.findall("./HEADER/UNITS_FOR_ENERGY")[0].attrib['UNITS']
   
    if Efermi_units=='Rydberg':
       Efermi_units='eV'
    else:
       sys.error('Energy units has to be in Rydbers')
   
    Efermi = float(root.findall("./HEADER/FERMI_ENERGY")[0].text.split()[0])*Ry2eV
   
    print('Fermi energy: {0:f} (eV)'.format(Efermi))
   
    nawf   =int(root.findall("./HEADER/NUMBER_OF_ATOMIC_WFC")[0].text.split()[0])
    print('Number of atomic wavefunctions: {0:d}'.format(nawf))
   
    U=None
    Sks=None
    my_eigsmat = None
   
    if read_eigs: 
       print('Reading eigenvalues with {0:d} processors'.format(nproc))
       my_eigsmat = np.zeros((nbnds,nkpnts,nspin))
       if nproc > 1:
          parallel   = True
       elif nproc == 1:
          parallel   = False
       else:
           sys.exit('Wrong number of processors')
   
   
       if parallel == True:
           for ispin in range(nspin):
               tic = time.time()
               my_eigsmat_list=read_eigenvalues_xml_par(nkpnts,Efermi,nspin,ispin,root,nproc)
   
               toc = time.time()
               hours, rem = divmod(toc-tic, 3600)
               minutes, seconds = divmod(rem, 60)
               print("Parallel parsing of eigenvalues[k] {:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds))
   
               tic = time.time()
               for ik in range(nkpnts):
                   my_eigsmat[:,ik,ispin]=my_eigsmat_list[ik]
               toc = time.time()
               hours, rem = divmod(toc-tic, 3600)
               minutes, seconds = divmod(rem, 60)
               print("Converting eigevalues[k] from lists to matrix {:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds))
   
   
       else:
           for ispin in range(nspin):
             for ik in range(nkpnts):
               if nspin==1:
                   eigk_type=root.findall("./EIGENVALUES/K-POINT.{0:d}/EIG".format(ik+1))[0].attrib['type']
               else:
                   eigk_type=root.findall("./EIGENVALUES/K-POINT.{0:d}/EIG.{1:d}".format(ik+1,ispin+1))[0].attrib['type']
               if eigk_type != 'real':
                 sys.exit('Reading eigenvalues that are not real numbers')
               if nspin==1:
                 eigk_file=np.array([float(i) for i in root.findall("./EIGENVALUES/K-POINT.{0:d}/EIG".format(ik+1))[0].text.split()])
               else:
                 eigk_file=np.array([float(i) for i in root.findall("./EIGENVALUES/K-POINT.{0:d}/EIG.{1:d}".format(ik+1,ispin+1))[0].text.split().split()])
               my_eigsmat[:,ik,ispin] = np.real(eigk_file)*Ry2eV-Efermi #meigs in eVs and wrt Ef
   
   
    if read_U:
       print('Reading projections with {0:d} processors'.format(nproc))
       Uaux    = np.zeros((nbnds,nawf, nkpnts,nspin),dtype=complex)
       U       = np.zeros((nawf, nbnds,nkpnts,nspin),dtype=complex)
       if nproc > 1:
          parallel   = True
       elif nproc == 1:
          parallel   = False
       else:
           sys.exit('Wrong number of processors')
   
       if parallel == True:
           for ispin in range(nspin):
               tic = time.time()
               Uaux_list      =read_projections_xml_par(nkpnts,nawf,nbnds,nspin,ispin,root,nproc)
               toc = time.time()
               hours, rem = divmod(toc-tic, 3600)
               minutes, seconds = divmod(rem, 60)
               print("Parallel parsing of U[k] {:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds))
   
               tic = time.time()
               for ik in range(nkpnts):
                   U[:,:,ik,ispin] = Uaux_list[ik]
               toc = time.time()
               hours, rem = divmod(toc-tic, 3600)
               minutes, seconds = divmod(rem, 60)
               print("Converting U[k] from lists to matrix {:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds))
   
   
       else:
           for ispin in range(nspin):
             for ik in range(nkpnts):
               for iin in range(nawf): #There will be nawf projections. Each projector of size nbnds x 1
                 if nspin==1:
                   wfc_type=root.findall("./PROJECTIONS/K-POINT.{0:d}/ATMWFC.{1:d}".format(ik+1,iin+1))[0].attrib['type']
                   aux     =root.findall("./PROJECTIONS/K-POINT.{0:d}/ATMWFC.{1:d}".format(ik+1,iin+1))[0].text
                 else:
                   wfc_type=root.findall("./PROJECTIONS/K-POINT.{0:d}/SPIN.{1:d}/ATMWFC.{2:d}".format(ik+1,iin+1))[0].attrib['type']
                   aux     =root.findall("./PROJECTIONS/K-POINT.{0:d}/SPIN.{1:d}/ATMWFC.{2:d}".format(ik+1,ispin+1,iin+1))[0].text
   
                 aux = np.array([float(i) for i in re.split(',|\n',aux.strip())])
   
                 if wfc_type=='real':
                   wfc = aux.reshape((nbnds,1))#wfc = nbnds x 1
                   Uaux[:,iin,ik,ispin] = wfc[:,0]
                 elif wfc_type=='complex':
                   wfc = aux.reshape((nbnds,2))
                   Uaux[:,iin,ik,ispin] = wfc[:,0]+1j*wfc[:,1]
                 else:
                   sys.exit('neither real nor complex??')
   
           for ispin in range(nspin):
             for ik in range(nkpnts):
               U[:,:,ik,ispin] = np.transpose(Uaux[:,:,ik,ispin]) #transpose of U. Now the columns of UU are the eigenvector of length nawf
   
       test = np.isnan(U)
       if True in test:
         sys.exit('Found a NaN projection coefficient. Crashing ...')
   
    if read_S:
        print('Reading overlap matrix')
        Sks  = np.zeros((nawf,nawf,nkpnts),dtype=complex)
        if parallel == True:
           tic = time.time()
           Sks_list = read_overlap_xml_par(nkpnts,nawf,root,nproc)
           toc = time.time()
           hours, rem = divmod(toc-tic, 3600)
           minutes, seconds = divmod(rem, 60)
           print("Parallel parsing of S[k] {:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds))
   
           tic = time.time()
           for ik in range(nkpnts):
               Sks[:,:,ik] = Sks_list[ik]
           toc = time.time()
           hours, rem = divmod(toc-tic, 3600)
           minutes, seconds = divmod(rem, 60)
           print("Converting S[k] list to matrix {:0>2}:{:0>2}:{:05.2f}".format(int(hours),int(minutes),seconds))
        else:
           for ik in range(nkpnts):
             ovlp_type = root.findall("./OVERLAPS/K-POINT.{0:d}/OVERLAP.1".format(ik+1))[0].attrib['type']
             aux = root.findall("./OVERLAPS/K-POINT.{0:d}/OVERLAP.1".format(ik+1))[0].text
             aux = np.array([float(i) for i in re.split(',|\n',aux.strip())])
   
             if ovlp_type !='complex':
               sys.exit('the overlaps are assumed to be complex numbers')
             if len(aux) != nawf**2*2:
               sys.exit('wrong number of elements when reading the S matrix')
   
             aux = aux.reshape((nawf**2,2))
             ovlp_vector = aux[:,0]+1j*aux[:,1]
             Sks_aux  = ovlp_vector.reshape((nawf,nawf),order='F')
             Sks[:,:,ik] = np.triu(Sks_aux,1)+np.diag(np.diag(Sks_aux))+np.conj(np.triu(Sks_aux,1)).T
  
    np.savez(QE_xml_data_file, \
             U=U, Sk=Sks, eigsmat=my_eigsmat, alat_units=alat_units, alat=alat, a_vectors_units=a_vectors_units, a_vectors=a_vectors, \
             nkpnts=nkpnts, nspin=nspin, kpnts=kpnts, kpnts_wght=kpnts_wght, \
             nbnds=nbnds, Efermi=Efermi, Efermi_units=Efermi_units, nawf=nawf, \
             nrot=nrot, nsym=nsym, invsym=invsym, symop=symop) #sym
    return(U,Sks, my_eigsmat, alat_units, alat, a_vectors_units, a_vectors, nkpnts, nspin,\
        kpnts, kpnts_wght, nbnds, Efermi, Efermi_units,nawf, \
        nrot, nsym, invsym, symop) #sym
def plot_compare_TB_DFT_eigs(Hks,my_eigsmat):
    import matplotlib.pyplot as plt
    import os

    nawf,nawf,nkpnts,nspin = Hks.shape
    nbnds_tb = nawf
    E_k = np.zeros((nbnds_tb,nkpnts,nspin))

    ispin = 0 #plots only 1 spin channel
    for ik in range(nkpnts):
        eigval,_ = la.eig(Hks[:,:,ik,ispin])
        E_k[:,ik,ispin] = np.sort(np.real(eigval))

    fig=plt.figure
    nbnds_dft,_,_=my_eigsmat.shape
    for i in range(nbnds_dft):
        yy = my_eigsmat[i,:,ispin]
        if i==0:
          plt.plot(yy,'-',linewidth=3,color='lime',label='DFT')
        else:
          plt.plot(yy,'-',linewidth=3,color='lime')

    for i in range(nbnds_tb):
        yy = E_k[i,:,ispin]
        if i==0:
          plt.plot(yy,'ok',markersize=2,markeredgecolor='None',label='TB')
        else:
          plt.plot(yy,'ok',markersize=2,markeredgecolor='None')

    plt.xlabel('k-points')
    plt.ylabel('Energy - E$_F$ (eV)')
    plt.legend()
    plt.title('Comparison of TB vs. DFT eigenvalues')
    plt.savefig('comparison.pdf',format='pdf')
