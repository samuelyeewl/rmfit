import numpy as np
import pandas as pd
import pyde
import pyde.de
import matplotlib.pyplot as plt
import emcee
import batman
import astropy.constants as aconst
import radvel
from .priors import PriorSet, UP, NP, JP, FP
from .likelihood import ll_normal_ev_py
from . import stats_help
from . import utils
from . import mcmc_help
from . import convective_blueshift

# Multiprocessing
from multiprocessing import Pool
import os
os.environ["OMP_NUM_THREADS"] = "1"

class LPFunction3(object):
    """
    Log-Likelihood function class
       
    NOTES:
        Based on hpprvi's class, see: https://github.com/hpparvi/exo_tutorials
    """
    def __init__(self,inp,file_priors):
        """
        INPUT:
            x - time values in BJD
            y - y values in m/s
            yerr - yerr values in m/s
            file_priors - prior file name
        """
        self.data1= {"time"   : inp['time1'],  
                     "y"   : inp['rv1'],   
                     "error"  : inp['e_rv1']}
        self.data2= {"time"   : inp['time2'],  
                     "y"   : inp['rv2'],   
                     "error"  : inp['e_rv2']}
        self.data3= {"time"   : inp['time3'],  
                     "y"   : inp['rv3'],   
                     "error"  : inp['e_rv3']}
        # Setting priors
        self.ps_all = priorset_from_file(file_priors) # all priors
        self.ps_fixed = PriorSet(np.array(self.ps_all.priors)[np.array(self.ps_all.fixed)]) # fixed priorset
        self.ps_vary  = PriorSet(np.array(self.ps_all.priors)[~np.array(self.ps_all.fixed)]) # varying priorset
        self.ps_fixed_dict = {key: val for key, val in zip(self.ps_fixed.labels,self.ps_fixed.args1)}
        print('Reading in priorfile from {}'.format(file_priors))
        print(self.ps_all.df)
        
    def get_jump_parameter_index(self,lab):
        """
        Get the index of a given label
        """
        return np.where(np.array(self.ps_vary.labels)==lab)[0][0]
    
    def get_jump_parameter_value(self,pv,lab):
        """
        Get the current value in the argument list 'pv' that has label 'lab'
        """
        # First check if we are actually varying it
        if lab in self.ps_vary.labels:
            return pv[self.get_jump_parameter_index(lab)]
        else:
            # We are not varying it
            return self.ps_fixed_dict[lab]
        
    def compute_rm_model(self,pv,times1=None,times2=None,times3=None):
        """
        Calls RM model and returns the transit model
        
        INPUT:
            pv    - parameters passed to the function 
            times - times, and array of timestamps 
        
        OUTPUT:
            lc - the lightcurve model at *times*
        """
        T0      =self.get_jump_parameter_value(pv,'t0_p1')
        P       =self.get_jump_parameter_value(pv,'P_p1')
        lam     =self.get_jump_parameter_value(pv,'lam_p1')
        vsini   =self.get_jump_parameter_value(pv,'vsini') 
        ii      =self.get_jump_parameter_value(pv,'inc_p1')
        rprs    =self.get_jump_parameter_value(pv,'p_p1')
        aRs     =self.get_jump_parameter_value(pv,'a_p1')
        u1      =self.get_jump_parameter_value(pv,'u1')
        u2      =self.get_jump_parameter_value(pv,'u2')
        gamma1  =self.get_jump_parameter_value(pv,'gamma1')
        gamma2  =self.get_jump_parameter_value(pv,'gamma2')
        gamma3  =self.get_jump_parameter_value(pv,'gamma3')
        beta    =self.get_jump_parameter_value(pv,'vbeta')
        #sigma   =self.get_jump_parameter_value(pv,'sigma')
        sigma   = vsini /1.31 # assume sigma is vsini/1.31 (see Hirano et al. 2010, 2011)
        e       =self.get_jump_parameter_value(pv,'ecc_p1')
        omega   =self.get_jump_parameter_value(pv,'omega_p1')
        exptime1=self.get_jump_parameter_value(pv,'exptime1')/86400. # exptime in days
        exptime2=self.get_jump_parameter_value(pv,'exptime2')/86400. # exptime in days
        exptime3=self.get_jump_parameter_value(pv,'exptime3')/86400. # exptime in days
        if times1 is None: times1 = self.data1["time"]
        if times2 is None: times2 = self.data2["time"]
        if times3 is None: times3 = self.data3["time"]
        self.rm1 = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime1,limb_dark='quadratic').evaluate(times1)
        self.rm2 = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime2,limb_dark='quadratic').evaluate(times2)
        self.rm3 = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime3,limb_dark='quadratic').evaluate(times3)
        return self.rm1, self.rm2, self.rm3

    #def compute_cb_model(self,pv,times=None):
    #    """
    #    Compute convective blueshift model

    #    NOTES:
    #        See Shporer & Brown 2011
    #    """
    #    ################
    #    # adding v_cb
    #    if times is None:
    #        times = self.data["x"]
    #    vcb    =self.get_jump_parameter_value(pv,'vcb')
    #    if vcb!=0:
    #        T0     =self.get_jump_parameter_value(pv,'t0_p1')
    #        P      =self.get_jump_parameter_value(pv,'P_p1')
    #        ii     =self.get_jump_parameter_value(pv,'inc_p1')
    #        rprs   =self.get_jump_parameter_value(pv,'p_p1')
    #        aRs    =self.get_jump_parameter_value(pv,'a_p1')
    #        u1     =self.get_jump_parameter_value(pv,'u1')
    #        u2     =self.get_jump_parameter_value(pv,'u2')
    #        e      =self.get_jump_parameter_value(pv,'ecc_p1')
    #        omega  =self.get_jump_parameter_value(pv,'omega_p1')

    #        # Calculate separation of centers
    #        x_1, y_1, z_1 = planet_XYZ_position(times,T0,P,aRs,ii,e,omega)
    #        ds = np.sqrt(x_1**2.+y_1**2.)

    #        self.vels_cb = convective_blueshift.cb_limbdark(ds,rprs,u1,u2,vcb,epsabs=1.49e-1,epsrel=1.49e-1)
    #        return self.vels_cb
    #    else:
    #        return np.zeros(len(times))
    #    ################
        
    def compute_rv_model(self,pv,times1=None,times2=None,times3=None):
        """
        Compute the RV model

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps 
        
        OUTPUT:
            rv - the rv model evaluated at 'times' if supplied, otherwise 
                      defaults to original data timestamps
        """
        if times1 is None: times1 = self.data1["time"]
        if times2 is None: times2 = self.data2["time"]
        if times3 is None: times3 = self.data3["time"]
        T0      = self.get_jump_parameter_value(pv,'t0_p1')
        P       = self.get_jump_parameter_value(pv,'P_p1')
        gamma1  = self.get_jump_parameter_value(pv,'gamma1')
        gamma2  = self.get_jump_parameter_value(pv,'gamma2')
        gamma3  = self.get_jump_parameter_value(pv,'gamma3')
        K       = self.get_jump_parameter_value(pv,'K_p1')
        e       = self.get_jump_parameter_value(pv,'ecc_p1')
        w       = self.get_jump_parameter_value(pv,'omega_p1')
        self.rv1 = get_rv_curve(times1,P=P,tc=T0,e=e,omega=w,K=K)+gamma1
        self.rv2 = get_rv_curve(times2,P=P,tc=T0,e=e,omega=w,K=K)+gamma2
        self.rv3 = get_rv_curve(times3,P=P,tc=T0,e=e,omega=w,K=K)+gamma3
        return self.rv1, self.rv2, self.rv3
        
    def compute_total_model(self,pv,times1=None,times2=None,times3=None):
        """
        Computes the full RM model (including RM and RV and CB)

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps 
        
        OUTPUT:
            rm - the rm model evaluated at 'times' if supplied, otherwise 
                      defaults to original data timestamps

        NOTES:
            see compute_rm_model(), compute_rv_model()
        """
        #return self.compute_rm_model(pv,times=times) + self.compute_rv_model(pv,times=times)
        rm1, rm2, rm3 = self.compute_rm_model(pv,times1=times1,times2=times2,times3=times3)
        rv1, rv2, rv3 = self.compute_rv_model(pv,times1=times1,times2=times2,times3=times3) #+ self.compute_cb_model(pv,times=times)
        return rm1+rv1, rm2+rv2, rm3+rv3
                    
    def __call__(self,pv):
        """
        Return the log likelihood

        INPUT:
            pv - the input list of varying parameters
        """
        if any(pv < self.ps_vary.pmins) or any(pv>self.ps_vary.pmaxs):
            return -np.inf

        ###############
        # Prepare data and model and error for ingestion into likelihood
        #y_data = self.data['y']
        y1, y2, y3 = self.compute_total_model(pv)
        # jitter in quadrature
        jitter1 = self.get_jump_parameter_value(pv,'sigma_rv1')
        jitter2 = self.get_jump_parameter_value(pv,'sigma_rv2')
        jitter3 = self.get_jump_parameter_value(pv,'sigma_rv3')
        error1 = np.sqrt(self.data1['error']**2.+jitter1**2.)
        error2 = np.sqrt(self.data2['error']**2.+jitter2**2.)
        error3 = np.sqrt(self.data3['error']**2.+jitter3**2.)
        ###############

        # Return the log-likelihood
        log_of_priors = self.ps_vary.c_log_prior(pv)
        # Calculate log likelihood
        #log_of_model  = ll_normal_ev_py(y_data, y_model, error)
        log_of_model1  = ll_normal_ev_py(self.data1["y"], y1, error1)
        log_of_model2  = ll_normal_ev_py(self.data2["y"], y2, error2)
        log_of_model3  = ll_normal_ev_py(self.data3["y"], y3, error3)
        log_ln = log_of_priors + log_of_model1 + log_of_model2 + log_of_model3
        return log_ln


class LPFunction2WithIStar(object):
    """
    Log-Likelihood function class
       
    NOTES:
        Based on hpprvi's class, see: https://github.com/hpparvi/exo_tutorials
    """
    def __init__(self,inp,file_priors):
        """
        INPUT:
            x - time values in BJD
            y - y values in m/s
            yerr - yerr values in m/s
            file_priors - prior file name
        """
        self.data1= {"time"   : inp['time1'],  
                     "y"      : inp['rv1'],   
                     "error"  : inp['e_rv1']}
        self.data2= {"time"   : inp['time2'],  
                     "y"      : inp['rv2'],   
                     "error"  : inp['e_rv2']}
        # Setting priors
        self.ps_all = priorset_from_file(file_priors) # all priors
        self.ps_fixed = PriorSet(np.array(self.ps_all.priors)[np.array(self.ps_all.fixed)]) # fixed priorset
        self.ps_vary  = PriorSet(np.array(self.ps_all.priors)[~np.array(self.ps_all.fixed)]) # varying priorset
        self.ps_fixed_dict = {key: val for key, val in zip(self.ps_fixed.labels,self.ps_fixed.args1)}
        print('Reading in priorfile from {}'.format(file_priors))
        print(self.ps_all.df)
        
    def get_jump_parameter_index(self,lab):
        """
        Get the index of a given label
        """
        return np.where(np.array(self.ps_vary.labels)==lab)[0][0]
    
    def get_jump_parameter_value(self,pv,lab):
        """
        Get the current value in the argument list 'pv' that has label 'lab'
        """
        # First check if we are actually varying it
        if lab in self.ps_vary.labels:
            return pv[self.get_jump_parameter_index(lab)]
        else:
            # We are not varying it
            return self.ps_fixed_dict[lab]
        
    def compute_rm_model(self,pv,times1=None,times2=None,times3=None):
        """
        Calls RM model and returns the transit model
        
        INPUT:
            pv    - parameters passed to the function 
            times - times, and array of timestamps 
        
        OUTPUT:
            lc - the lightcurve model at *times*
        """
        T0      =self.get_jump_parameter_value(pv,'t0_p1')
        P       =self.get_jump_parameter_value(pv,'P_p1')
        lam     =self.get_jump_parameter_value(pv,'lam_p1')
        cosi    = self.get_jump_parameter_value(pv,'cosi')
        R       = self.get_jump_parameter_value(pv,'rstar')
        Prot    = self.get_jump_parameter_value(pv,'Prot')
        veq = (2.*np.pi*R*aconst.R_sun.value)/(Prot*86400.*1000.) # km/s
        vsini   = veq*np.sqrt(1.-cosi**2.)
        #vsini   =self.get_jump_parameter_value(pv,'vsini') 
        ii      =self.get_jump_parameter_value(pv,'inc_p1')
        rprs    =self.get_jump_parameter_value(pv,'p_p1')
        aRs     =self.get_jump_parameter_value(pv,'a_p1')
        u1      =self.get_jump_parameter_value(pv,'u1')
        u2      =self.get_jump_parameter_value(pv,'u2')
        #q1      =self.get_jump_parameter_value(pv,'q1')
        #q2      =self.get_jump_parameter_value(pv,'q2')
        #u1, u2 = u1_u2_from_q1_q2(q1,q2)
        gamma1  =self.get_jump_parameter_value(pv,'gamma1')
        gamma2  =self.get_jump_parameter_value(pv,'gamma2')
        beta    =self.get_jump_parameter_value(pv,'vbeta')
        #sigma   =self.get_jump_parameter_value(pv,'sigma')
        sigma   = vsini /1.31 # assume sigma is vsini/1.31 (see Hirano et al. 2010, 2011)
        e       =self.get_jump_parameter_value(pv,'ecc_p1')
        omega   =self.get_jump_parameter_value(pv,'omega_p1')
        exptime1=self.get_jump_parameter_value(pv,'exptime1')/86400. # exptime in days
        exptime2=self.get_jump_parameter_value(pv,'exptime2')/86400. # exptime in days
        if times1 is None: times1 = self.data1["time"]
        if times2 is None: times2 = self.data2["time"]
        self.rm1 = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime1,limb_dark='quadratic').evaluate(times1)
        self.rm2 = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime2,limb_dark='quadratic').evaluate(times2)
        return self.rm1, self.rm2

    #def compute_cb_model(self,pv,times=None):
    #    """
    #    Compute convective blueshift model

    #    NOTES:
    #        See Shporer & Brown 2011
    #    """
    #    ################
    #    # adding v_cb
    #    if times is None:
    #        times = self.data["x"]
    #    vcb    =self.get_jump_parameter_value(pv,'vcb')
    #    if vcb!=0:
    #        T0     =self.get_jump_parameter_value(pv,'t0_p1')
    #        P      =self.get_jump_parameter_value(pv,'P_p1')
    #        ii     =self.get_jump_parameter_value(pv,'inc_p1')
    #        rprs   =self.get_jump_parameter_value(pv,'p_p1')
    #        aRs    =self.get_jump_parameter_value(pv,'a_p1')
    #        u1     =self.get_jump_parameter_value(pv,'u1')
    #        u2     =self.get_jump_parameter_value(pv,'u2')
    #        e      =self.get_jump_parameter_value(pv,'ecc_p1')
    #        omega  =self.get_jump_parameter_value(pv,'omega_p1')

    #        # Calculate separation of centers
    #        x_1, y_1, z_1 = planet_XYZ_position(times,T0,P,aRs,ii,e,omega)
    #        ds = np.sqrt(x_1**2.+y_1**2.)

    #        self.vels_cb = convective_blueshift.cb_limbdark(ds,rprs,u1,u2,vcb,epsabs=1.49e-1,epsrel=1.49e-1)
    #        return self.vels_cb
    #    else:
    #        return np.zeros(len(times))
    #    ################
        
    def compute_rv_model(self,pv,times1=None,times2=None,times3=None):
        """
        Compute the RV model

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps 
        
        OUTPUT:
            rv - the rv model evaluated at 'times' if supplied, otherwise 
                      defaults to original data timestamps
        """
        if times1 is None: times1 = self.data1["time"]
        if times2 is None: times2 = self.data2["time"]
        T0      = self.get_jump_parameter_value(pv,'t0_p1')
        P       = self.get_jump_parameter_value(pv,'P_p1')
        gamma1  = self.get_jump_parameter_value(pv,'gamma1')
        gamma2  = self.get_jump_parameter_value(pv,'gamma2')
        K       = self.get_jump_parameter_value(pv,'K_p1')
        e       = self.get_jump_parameter_value(pv,'ecc_p1')
        w       = self.get_jump_parameter_value(pv,'omega_p1')
        self.rv1 = get_rv_curve(times1,P=P,tc=T0,e=e,omega=w,K=K)+gamma1
        self.rv2 = get_rv_curve(times2,P=P,tc=T0,e=e,omega=w,K=K)+gamma2
        return self.rv1, self.rv2
        
    def compute_total_model(self,pv,times1=None,times2=None,times3=None):
        """
        Computes the full RM model (including RM and RV and CB)

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps 
        
        OUTPUT:
            rm - the rm model evaluated at 'times' if supplied, otherwise 
                      defaults to original data timestamps

        NOTES:
            see compute_rm_model(), compute_rv_model()
        """
        #return self.compute_rm_model(pv,times=times) + self.compute_rv_model(pv,times=times)
        rm1, rm2 = self.compute_rm_model(pv,times1=times1,times2=times2)
        rv1, rv2 = self.compute_rv_model(pv,times1=times1,times2=times2) #+ self.compute_cb_model(pv,times=times)
        return rm1+rv1, rm2+rv2

    #def compute_veq(self,pv):
    #    """
    #    """
    #    cosi    = self.get_jump_parameter_value(pv,'cosi')
    #    R       = self.get_jump_parameter_value(pv,'rstar')
    #    Prot    = self.get_jump_parameter_value(pv,'Prot')
    #    veq = (2.*np.pi*R*aconst.R_sun.value)/(Prot*86400.*1000.) # km/s
    #    return veq
                    
    def __call__(self,pv):
        """
        Return the log likelihood

        INPUT:
            pv - the input list of varying parameters
        """
        if any(pv < self.ps_vary.pmins) or any(pv>self.ps_vary.pmaxs):
            return -np.inf

        ii =self.get_jump_parameter_value(pv,'inc_p1')
        if ii > 90:
            return -np.inf

        ###############
        # Prepare data and model and error for ingestion into likelihood
        #y_data = self.data['y']
        y1, y2 = self.compute_total_model(pv)
        # jitter in quadrature
        jitter1 = self.get_jump_parameter_value(pv,'sigma_rv1')
        jitter2 = self.get_jump_parameter_value(pv,'sigma_rv2')
        error1 = np.sqrt(self.data1['error']**2.+jitter1**2.)
        error2 = np.sqrt(self.data2['error']**2.+jitter2**2.)
        ###############

        # Return the log-likelihood
        log_of_priors = self.ps_vary.c_log_prior(pv)
        # Calculate log likelihood
        #log_of_model  = ll_normal_ev_py(y_data, y_model, error)
        log_of_model1  = ll_normal_ev_py(self.data1["y"], y1, error1)
        log_of_model2  = ll_normal_ev_py(self.data2["y"], y2, error2)
        log_ln = log_of_priors + log_of_model1 + log_of_model2 
        return log_ln

class LPFunction2(object):
    """
    Log-Likelihood function class
       
    NOTES:
        Based on hpprvi's class, see: https://github.com/hpparvi/exo_tutorials
    """
    def __init__(self,inp,file_priors):
        """
        INPUT:
            x - time values in BJD
            y - y values in m/s
            yerr - yerr values in m/s
            file_priors - prior file name
        """
        self.data1= {"time"   : inp['time1'],  
                     "y"   : inp['rv1'],   
                     "error"  : inp['e_rv1']}
        self.data2= {"time"   : inp['time2'],  
                     "y"   : inp['rv2'],   
                     "error"  : inp['e_rv2']}
        # Setting priors
        self.ps_all = priorset_from_file(file_priors) # all priors
        self.ps_fixed = PriorSet(np.array(self.ps_all.priors)[np.array(self.ps_all.fixed)]) # fixed priorset
        self.ps_vary  = PriorSet(np.array(self.ps_all.priors)[~np.array(self.ps_all.fixed)]) # varying priorset
        self.ps_fixed_dict = {key: val for key, val in zip(self.ps_fixed.labels,self.ps_fixed.args1)}
        print('Reading in priorfile from {}'.format(file_priors))
        print(self.ps_all.df)
        
    def get_jump_parameter_index(self,lab):
        """
        Get the index of a given label
        """
        return np.where(np.array(self.ps_vary.labels)==lab)[0][0]
    
    def get_jump_parameter_value(self,pv,lab):
        """
        Get the current value in the argument list 'pv' that has label 'lab'
        """
        # First check if we are actually varying it
        if lab in self.ps_vary.labels:
            return pv[self.get_jump_parameter_index(lab)]
        else:
            # We are not varying it
            return self.ps_fixed_dict[lab]
        
    def compute_rm_model(self,pv,times1=None,times2=None,times3=None):
        """
        Calls RM model and returns the transit model
        
        INPUT:
            pv    - parameters passed to the function 
            times - times, and array of timestamps 
        
        OUTPUT:
            lc - the lightcurve model at *times*
        """
        T0      =self.get_jump_parameter_value(pv,'t0_p1')
        P       =self.get_jump_parameter_value(pv,'P_p1')
        lam     =self.get_jump_parameter_value(pv,'lam_p1')
        vsini   =self.get_jump_parameter_value(pv,'vsini') 
        ii      =self.get_jump_parameter_value(pv,'inc_p1')
        rprs    =self.get_jump_parameter_value(pv,'p_p1')
        aRs     =self.get_jump_parameter_value(pv,'a_p1')
        u1      =self.get_jump_parameter_value(pv,'u1')
        u2      =self.get_jump_parameter_value(pv,'u2')
        #q1      =self.get_jump_parameter_value(pv,'q1')
        #q2      =self.get_jump_parameter_value(pv,'q2')
        #u1, u2 = u1_u2_from_q1_q2(q1,q2)
        gamma1  =self.get_jump_parameter_value(pv,'gamma1')
        gamma2  =self.get_jump_parameter_value(pv,'gamma2')
        beta    =self.get_jump_parameter_value(pv,'vbeta')
        #sigma   =self.get_jump_parameter_value(pv,'sigma')
        sigma   = vsini /1.31 # assume sigma is vsini/1.31 (see Hirano et al. 2010, 2011)
        e       =self.get_jump_parameter_value(pv,'ecc_p1')
        omega   =self.get_jump_parameter_value(pv,'omega_p1')
        exptime1=self.get_jump_parameter_value(pv,'exptime1')/86400. # exptime in days
        exptime2=self.get_jump_parameter_value(pv,'exptime2')/86400. # exptime in days
        if times1 is None: times1 = self.data1["time"]
        if times2 is None: times2 = self.data2["time"]
        self.rm1 = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime1,limb_dark='quadratic').evaluate(times1)
        self.rm2 = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime2,limb_dark='quadratic').evaluate(times2)
        return self.rm1, self.rm2

    #def compute_cb_model(self,pv,times=None):
    #    """
    #    Compute convective blueshift model

    #    NOTES:
    #        See Shporer & Brown 2011
    #    """
    #    ################
    #    # adding v_cb
    #    if times is None:
    #        times = self.data["x"]
    #    vcb    =self.get_jump_parameter_value(pv,'vcb')
    #    if vcb!=0:
    #        T0     =self.get_jump_parameter_value(pv,'t0_p1')
    #        P      =self.get_jump_parameter_value(pv,'P_p1')
    #        ii     =self.get_jump_parameter_value(pv,'inc_p1')
    #        rprs   =self.get_jump_parameter_value(pv,'p_p1')
    #        aRs    =self.get_jump_parameter_value(pv,'a_p1')
    #        u1     =self.get_jump_parameter_value(pv,'u1')
    #        u2     =self.get_jump_parameter_value(pv,'u2')
    #        e      =self.get_jump_parameter_value(pv,'ecc_p1')
    #        omega  =self.get_jump_parameter_value(pv,'omega_p1')

    #        # Calculate separation of centers
    #        x_1, y_1, z_1 = planet_XYZ_position(times,T0,P,aRs,ii,e,omega)
    #        ds = np.sqrt(x_1**2.+y_1**2.)

    #        self.vels_cb = convective_blueshift.cb_limbdark(ds,rprs,u1,u2,vcb,epsabs=1.49e-1,epsrel=1.49e-1)
    #        return self.vels_cb
    #    else:
    #        return np.zeros(len(times))
    #    ################
        
    def compute_rv_model(self,pv,times1=None,times2=None,times3=None):
        """
        Compute the RV model

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps 
        
        OUTPUT:
            rv - the rv model evaluated at 'times' if supplied, otherwise 
                      defaults to original data timestamps
        """
        if times1 is None: times1 = self.data1["time"]
        if times2 is None: times2 = self.data2["time"]
        T0      = self.get_jump_parameter_value(pv,'t0_p1')
        P       = self.get_jump_parameter_value(pv,'P_p1')
        gamma1  = self.get_jump_parameter_value(pv,'gamma1')
        gamma2  = self.get_jump_parameter_value(pv,'gamma2')
        K       = self.get_jump_parameter_value(pv,'K_p1')
        e       = self.get_jump_parameter_value(pv,'ecc_p1')
        w       = self.get_jump_parameter_value(pv,'omega_p1')
        self.rv1 = get_rv_curve(times1,P=P,tc=T0,e=e,omega=w,K=K)+gamma1
        self.rv2 = get_rv_curve(times2,P=P,tc=T0,e=e,omega=w,K=K)+gamma2
        return self.rv1, self.rv2
        
    def compute_total_model(self,pv,times1=None,times2=None,times3=None):
        """
        Computes the full RM model (including RM and RV and CB)

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps 
        
        OUTPUT:
            rm - the rm model evaluated at 'times' if supplied, otherwise 
                      defaults to original data timestamps

        NOTES:
            see compute_rm_model(), compute_rv_model()
        """
        #return self.compute_rm_model(pv,times=times) + self.compute_rv_model(pv,times=times)
        rm1, rm2 = self.compute_rm_model(pv,times1=times1,times2=times2)
        rv1, rv2 = self.compute_rv_model(pv,times1=times1,times2=times2) #+ self.compute_cb_model(pv,times=times)
        return rm1+rv1, rm2+rv2
                    
    def __call__(self,pv):
        """
        Return the log likelihood

        INPUT:
            pv - the input list of varying parameters
        """
        if any(pv < self.ps_vary.pmins) or any(pv>self.ps_vary.pmaxs):
            return -np.inf

        ii =self.get_jump_parameter_value(pv,'inc_p1')
        if ii > 90:
            return -np.inf

        ###############
        # Prepare data and model and error for ingestion into likelihood
        #y_data = self.data['y']
        y1, y2 = self.compute_total_model(pv)
        # jitter in quadrature
        jitter1 = self.get_jump_parameter_value(pv,'sigma_rv1')
        jitter2 = self.get_jump_parameter_value(pv,'sigma_rv2')
        error1 = np.sqrt(self.data1['error']**2.+jitter1**2.)
        error2 = np.sqrt(self.data2['error']**2.+jitter2**2.)
        ###############

        # Return the log-likelihood
        log_of_priors = self.ps_vary.c_log_prior(pv)
        # Calculate log likelihood
        #log_of_model  = ll_normal_ev_py(y_data, y_model, error)
        log_of_model1  = ll_normal_ev_py(self.data1["y"], y1, error1)
        log_of_model2  = ll_normal_ev_py(self.data2["y"], y2, error2)
        log_ln = log_of_priors + log_of_model1 + log_of_model2 
        return log_ln

class LPFunctionWithIStar(object):
    """
    Log-Likelihood function class

    NOTES:
        Based on hpprvi's class, see: https://github.com/hpparvi/exo_tutorials
    """
    def __init__(self,x,y,yerr,file_priors):
        """
        INPUT:
            x - time values in BJD
            y - y values in m/s
            yerr - yerr values in m/s
            file_priors - prior file name
        """
        self.data= {"x"   : x,
                    "y"   : y,
                    "error"  : yerr}
        # Setting priors
        self.ps_all = priorset_from_file(file_priors) # all priors
        self.ps_fixed = PriorSet(np.array(self.ps_all.priors)[np.array(self.ps_all.fixed)]) # fixed priorset
        self.ps_vary  = PriorSet(np.array(self.ps_all.priors)[~np.array(self.ps_all.fixed)]) # varying priorset
        self.ps_fixed_dict = {key: val for key, val in zip(self.ps_fixed.labels,self.ps_fixed.args1)}
        print('Reading in priorfile from {}'.format(file_priors))
        print(self.ps_all.df)

    def get_jump_parameter_index(self,lab):
        """
        Get the index of a given label
        """
        return np.where(np.array(self.ps_vary.labels)==lab)[0][0]

    def get_jump_parameter_value(self,pv,lab):
        """
        Get the current value in the argument list 'pv' that has label 'lab'
        """
        # First check if we are actually varying it
        if lab in self.ps_vary.labels:
            return pv[self.get_jump_parameter_index(lab)]
        else:
            # We are not varying it
            return self.ps_fixed_dict[lab]

    def compute_rm_model(self,pv,times=None):
        """
        Calls RM model and returns the transit model

        INPUT:
            pv    - parameters passed to the function
            times - times, and array of timestamps

        OUTPUT:
            lc - the lightcurve model at *times*
        """
        T0     =self.get_jump_parameter_value(pv,'t0_p1')
        P      =self.get_jump_parameter_value(pv,'P_p1')
        lam    =self.get_jump_parameter_value(pv,'lam_p1')
        cosi    = self.get_jump_parameter_value(pv,'cosi')
        R       = self.get_jump_parameter_value(pv,'rstar')
        Prot    = self.get_jump_parameter_value(pv,'Prot')
        veq = (2.*np.pi*R*aconst.R_sun.value)/(Prot*86400.*1000.) # km/s
        vsini   = veq*np.sqrt(1.-cosi**2.)
        #vsini  =self.get_jump_parameter_value(pv,'vsini')
        ii     =self.get_jump_parameter_value(pv,'inc_p1')
        rprs   =self.get_jump_parameter_value(pv,'p_p1')
        aRs    =self.get_jump_parameter_value(pv,'a_p1')
        u1     =self.get_jump_parameter_value(pv,'u1')
        u2     =self.get_jump_parameter_value(pv,'u2')
        gamma  =self.get_jump_parameter_value(pv,'gamma')
        beta   =self.get_jump_parameter_value(pv,'vbeta')
        #sigma  =self.get_jump_parameter_value(pv,'sigma')
        sigma  = vsini /1.31 # assume sigma is vsini/1.31 (see Hirano et al. 2010, 2011)
        e      =self.get_jump_parameter_value(pv,'ecc_p1')
        omega  =self.get_jump_parameter_value(pv,'omega_p1')
        exptime=self.get_jump_parameter_value(pv,'exptime')/86400. # exptime in days
        if times is None:
            times = self.data["x"]
        self.RH = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime,limb_dark='quadratic')
        self.rm = self.RH.evaluate(times)
        return self.rm

    def compute_cb_model(self,pv,times=None):
        """
        Compute convective blueshift model

        NOTES:
            See Shporer & Brown 2011
        """
        ################
        # adding v_cb
        if times is None:
            times = self.data["x"]
        vcb    =self.get_jump_parameter_value(pv,'vcb')
        if vcb!=0:
            T0     =self.get_jump_parameter_value(pv,'t0_p1')
            P      =self.get_jump_parameter_value(pv,'P_p1')
            ii     =self.get_jump_parameter_value(pv,'inc_p1')
            rprs   =self.get_jump_parameter_value(pv,'p_p1')
            aRs    =self.get_jump_parameter_value(pv,'a_p1')
            u1     =self.get_jump_parameter_value(pv,'u1')
            u2     =self.get_jump_parameter_value(pv,'u2')
            e      =self.get_jump_parameter_value(pv,'ecc_p1')
            omega  =self.get_jump_parameter_value(pv,'omega_p1')

            # Calculate separation of centers
            x_1, y_1, z_1 = planet_XYZ_position(times,T0,P,aRs,ii,e,omega)
            ds = np.sqrt(x_1**2.+y_1**2.)

            self.vels_cb = convective_blueshift.cb_limbdark(ds,rprs,u1,u2,vcb,epsabs=1.49e-1,epsrel=1.49e-1)
            return self.vels_cb
        else:
            return np.zeros(len(times))
        ################
        
    def compute_rv_model(self,pv,times=None):
        """
        Compute the RV model

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rv - the rv model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]
        T0      = self.get_jump_parameter_value(pv,'t0_p1')
        P       = self.get_jump_parameter_value(pv,'P_p1')
        gamma   = self.get_jump_parameter_value(pv,'gamma')
        K       = self.get_jump_parameter_value(pv,'K_p1')
        e       = self.get_jump_parameter_value(pv,'ecc_p1')
        w       = self.get_jump_parameter_value(pv,'omega_p1')
        self.rv = get_rv_curve(times,P=P,tc=T0,e=e,omega=w,K=K)+gamma
        return self.rv

    def compute_polynomial_model(self,pv,times=None):
        """
        Compute the polynomial model.  Note that if gammadot and gammadotdot
        are not specified in the priors file, they both default to zero.

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            poly - the polynomial model evaluated at 'times' if supplied,
                   otherwise defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]

        #T0 = self.get_jump_parameter_value(pv,'t0_p1')
        T0 = (self.data['x'][0] + self.data['x'][-1])/2.
        try:
            gammadot = self.get_jump_parameter_value(pv,'gammadot')
        except KeyError as e:
            gammadot = 0
        try:
            gammadotdot = self.get_jump_parameter_value(pv,'gammadotdot')
        except KeyError as e:
            gammadotdot = 0

        self.poly = (
            gammadot * (times - T0) +
            gammadotdot * (times - T0)**2
        )
        return self.poly

    def compute_total_model(self,pv,times=None):
        """
        Computes the full RM model (including RM and RV and CB)

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rm - the rm model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps

        NOTES:
            see compute_rm_model(), compute_rv_model(),
            compute_polynomial_model()
        """
        return (
            self.compute_rm_model(pv,times=times) +
            self.compute_rv_model(pv,times=times) +
            self.compute_polynomial_model(pv,times=times) +
            self.compute_cb_model(pv,times=times)
        )

    def __call__(self,pv):
        """
        Return the log likelihood

        INPUT:
            pv - the input list of varying parameters
        """
        if any(pv < self.ps_vary.pmins) or any(pv>self.ps_vary.pmaxs):
            return -np.inf

        ii =self.get_jump_parameter_value(pv,'inc_p1')
        if ii > 90:
            return -np.inf

        ###############
        # Prepare data and model and error for ingestion into likelihood
        y_data = self.data['y']
        y_model = self.compute_total_model(pv)
        # jitter in quadrature
        jitter = self.get_jump_parameter_value(pv,'sigma_rv')
        error = np.sqrt(self.data['error']**2.+jitter**2.)
        ###############

        # Return the log-likelihood
        log_of_priors = self.ps_vary.c_log_prior(pv)
        # Calculate log likelihood
        log_of_model  = ll_normal_ev_py(y_data, y_model, error)
        log_ln = log_of_priors + log_of_model
        return log_ln

        
class LPFunctionEcc(object):
    """
    Log-Likelihood function class

    NOTES:
        Based on hpprvi's class, see: https://github.com/hpparvi/exo_tutorials
    """
    def __init__(self,x,y,yerr,file_priors):
        """
        INPUT:
            x - time values in BJD
            y - y values in m/s
            yerr - yerr values in m/s
            file_priors - prior file name
        """
        self.data= {"x"   : x,
                    "y"   : y,
                    "error"  : yerr}
        # Setting priors
        self.ps_all = priorset_from_file(file_priors) # all priors
        self.ps_fixed = PriorSet(np.array(self.ps_all.priors)[np.array(self.ps_all.fixed)]) # fixed priorset
        self.ps_vary  = PriorSet(np.array(self.ps_all.priors)[~np.array(self.ps_all.fixed)]) # varying priorset
        self.ps_fixed_dict = {key: val for key, val in zip(self.ps_fixed.labels,self.ps_fixed.args1)}
        print('Reading in priorfile from {}'.format(file_priors))
        print(self.ps_all.df)

    def get_jump_parameter_index(self,lab):
        """
        Get the index of a given label
        """
        return np.where(np.array(self.ps_vary.labels)==lab)[0][0]

    def get_jump_parameter_value(self,pv,lab):
        """
        Get the current value in the argument list 'pv' that has label 'lab'
        """
        # First check if we are actually varying it
        if lab in self.ps_vary.labels:
            return pv[self.get_jump_parameter_index(lab)]
        else:
            # We are not varying it
            return self.ps_fixed_dict[lab]

    def compute_rm_model(self,pv,times=None):
        """
        Calls RM model and returns the transit model

        INPUT:
            pv    - parameters passed to the function
            times - times, and array of timestamps

        OUTPUT:
            lc - the lightcurve model at *times*
        """
        T0     =self.get_jump_parameter_value(pv,'t0_p1')
        P      =self.get_jump_parameter_value(pv,'P_p1')
        lam    =self.get_jump_parameter_value(pv,'lam_p1')
        vsini  =self.get_jump_parameter_value(pv,'vsini')
        ii     =self.get_jump_parameter_value(pv,'inc_p1')
        rprs   =self.get_jump_parameter_value(pv,'p_p1')
        aRs    =self.get_jump_parameter_value(pv,'a_p1')
        u1     =self.get_jump_parameter_value(pv,'u1')
        u2     =self.get_jump_parameter_value(pv,'u2')
        gamma  =self.get_jump_parameter_value(pv,'gamma')
        beta   =self.get_jump_parameter_value(pv,'vbeta')
        #sigma  =self.get_jump_parameter_value(pv,'sigma')
        sigma  = vsini /1.31 # assume sigma is vsini/1.31 (see Hirano et al. 2010, 2011)
        secosw =self.get_jump_parameter_value(pv,'secosw_p1')
        sesinw =self.get_jump_parameter_value(pv,'sesinw_p1')
        e      =np.sqrt(secosw**2. + sesinw**2.)
        omega  =np.arctan2(sesinw,secosw)
        # e      =self.get_jump_parameter_value(pv,'ecc_p1')
        # omega  =self.get_jump_parameter_value(pv,'omega_p1')
        exptime=self.get_jump_parameter_value(pv,'exptime')/86400. # exptime in days
        if times is None:
            times = self.data["x"]
        self.RH = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime,limb_dark='quadratic')
        self.rm = self.RH.evaluate(times)
        return self.rm

    def compute_cb_model(self,pv,times=None):
        """
        Compute convective blueshift model

        NOTES:
            See Shporer & Brown 2011
        """
        ################
        # adding v_cb
        if times is None:
            times = self.data["x"]
        vcb    =self.get_jump_parameter_value(pv,'vcb')
        if vcb!=0:
            T0     =self.get_jump_parameter_value(pv,'t0_p1')
            P      =self.get_jump_parameter_value(pv,'P_p1')
            ii     =self.get_jump_parameter_value(pv,'inc_p1')
            rprs   =self.get_jump_parameter_value(pv,'p_p1')
            aRs    =self.get_jump_parameter_value(pv,'a_p1')
            u1     =self.get_jump_parameter_value(pv,'u1')
            u2     =self.get_jump_parameter_value(pv,'u2')
            secosw =self.get_jump_parameter_value(pv,'secosw_p1')
            sesinw =self.get_jump_parameter_value(pv,'sesinw_p1')
            e      =np.sqrt(secosw**2. + sesinw**2.)
            omega  =np.arctan2(sesinw,secosw)
            # e      =self.get_jump_parameter_value(pv,'ecc_p1')
            # omega  =self.get_jump_parameter_value(pv,'omega_p1')

            # Calculate separation of centers
            x_1, y_1, z_1 = planet_XYZ_position(times,T0,P,aRs,ii,e,omega)
            ds = np.sqrt(x_1**2.+y_1**2.)

            self.vels_cb = convective_blueshift.cb_limbdark(ds,rprs,u1,u2,vcb,epsabs=1.49e-1,epsrel=1.49e-1)
            return self.vels_cb
        else:
            return np.zeros(len(times))
        ################
        
    def compute_rv_model(self,pv,times=None):
        """
        Compute the RV model

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rv - the rv model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]
        T0      = self.get_jump_parameter_value(pv,'t0_p1')
        P       = self.get_jump_parameter_value(pv,'P_p1')
        gamma   = self.get_jump_parameter_value(pv,'gamma')
        K       = self.get_jump_parameter_value(pv,'K_p1')
        secosw  =self.get_jump_parameter_value(pv,'secosw_p1')
        sesinw  =self.get_jump_parameter_value(pv,'sesinw_p1')
        e       =np.sqrt(secosw**2. + sesinw**2.)
        omega   =np.arctan2(sesinw,secosw)
        # e       = self.get_jump_parameter_value(pv,'ecc_p1')
        # w       = self.get_jump_parameter_value(pv,'omega_p1')
        self.rv = get_rv_curve(times,P=P,tc=T0,e=e,omega=omega,K=K)+gamma
        return self.rv

    def compute_polynomial_model(self,pv,times=None):
        """
        Compute the polynomial model.  Note that if gammadot and gammadotdot
        are not specified in the priors file, they both default to zero.

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            poly - the polynomial model evaluated at 'times' if supplied,
                   otherwise defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]

        #T0 = self.get_jump_parameter_value(pv,'t0_p1')
        # Use Mean of data instead
        T0 = (self.data['x'][0] + self.data['x'][-1])/2.
        try:
            gammadot = self.get_jump_parameter_value(pv,'gammadot')
        except KeyError as e:
            gammadot = 0
        try:
            gammadotdot = self.get_jump_parameter_value(pv,'gammadotdot')
        except KeyError as e:
            gammadotdot = 0

        self.poly = (
            gammadot * (times - T0) +
            gammadotdot * (times - T0)**2
        )
        return self.poly

    def compute_total_model(self,pv,times=None):
        """
        Computes the full RM model (including RM and RV and CB)

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rm - the rm model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps

        NOTES:
            see compute_rm_model(), compute_rv_model(),
            compute_polynomial_model()
        """
        return (
            self.compute_rm_model(pv,times=times) +
            self.compute_rv_model(pv,times=times) +
            self.compute_polynomial_model(pv,times=times) +
            self.compute_cb_model(pv,times=times)
        )

    def __call__(self,pv):
        """
        Return the log likelihood

        INPUT:
            pv - the input list of varying parameters
        """
        if any(pv < self.ps_vary.pmins) or any(pv>self.ps_vary.pmaxs):
            return -np.inf

        ii =self.get_jump_parameter_value(pv,'inc_p1')
        if ii > 90:
            return -np.inf

        ###############
        # Prepare data and model and error for ingestion into likelihood
        y_data = self.data['y']
        y_model = self.compute_total_model(pv)
        # jitter in quadrature
        jitter = self.get_jump_parameter_value(pv,'sigma_rv')
        error = np.sqrt(self.data['error']**2.+jitter**2.)
        ###############

        # Return the log-likelihood
        log_of_priors = self.ps_vary.c_log_prior(pv)
        # Calculate log likelihood
        log_of_model  = ll_normal_ev_py(y_data, y_model, error)
        log_ln = log_of_priors + log_of_model
        return log_ln

        
class LPFunctionTransObs(object):
    """
    Log-Likelihood function class

    Parameterizes in terms of transit observables:
    - Tdur: Transit duration (first to fourth contacts)
    - Tfull: Duration of full transit (second to third contacts)

    NOTES:
        Based on hpprvi's class, see: https://github.com/hpparvi/exo_tutorials
    """
    def __init__(self,x,y,yerr,file_priors):
        """
        INPUT:
            x - time values in BJD
            y - y values in m/s
            yerr - yerr values in m/s
            file_priors - prior file name
        """
        self.data= {"x"   : x,
                    "y"   : y,
                    "error"  : yerr}
        # Setting priors
        self.ps_all = priorset_from_file(file_priors) # all priors
        self.ps_fixed = PriorSet(np.array(self.ps_all.priors)[np.array(self.ps_all.fixed)]) # fixed priorset
        self.ps_vary  = PriorSet(np.array(self.ps_all.priors)[~np.array(self.ps_all.fixed)]) # varying priorset
        self.ps_fixed_dict = {key: val for key, val in zip(self.ps_fixed.labels,self.ps_fixed.args1)}
        print('Reading in priorfile from {}'.format(file_priors))
        print(self.ps_all.df)

    def get_jump_parameter_index(self,lab):
        """
        Get the index of a given label
        """
        return np.where(np.array(self.ps_vary.labels)==lab)[0][0]

    def get_jump_parameter_value(self,pv,lab):
        """
        Get the current value in the argument list 'pv' that has label 'lab'
        """
        # First check if we are actually varying it
        if lab in self.ps_vary.labels:
            return pv[self.get_jump_parameter_index(lab)]
        else:
            # We are not varying it
            return self.ps_fixed_dict[lab]

    def compute_rm_model(self,pv,times=None):
        """
        Calls RM model and returns the transit model

        INPUT:
            pv    - parameters passed to the function
            times - times, and array of timestamps

        OUTPUT:
            lc - the lightcurve model at *times*
        """
        T0     =self.get_jump_parameter_value(pv,'t0_p1')
        P      =self.get_jump_parameter_value(pv,'P_p1')
        lam    =self.get_jump_parameter_value(pv,'lam_p1')
        vsini  =self.get_jump_parameter_value(pv,'vsini')
        rprs   =self.get_jump_parameter_value(pv,'p_p1')
        # ii     =self.get_jump_parameter_value(pv,'inc_p1')
        # aRs    =self.get_jump_parameter_value(pv,'a_p1')
        # Tdur and tau replace a/Rstar and inclination
        Tdur   =self.get_jump_parameter_value(pv,'Tdur_p1')
        Tfull  =self.get_jump_parameter_value(pv,'Tfull_p1')
        # tau    =self.get_jump_parameter_value(pv,'tau_p1')
        u1     =self.get_jump_parameter_value(pv,'u1')
        u2     =self.get_jump_parameter_value(pv,'u2')
        gamma  =self.get_jump_parameter_value(pv,'gamma')
        beta   =self.get_jump_parameter_value(pv,'vbeta')
        #sigma  =self.get_jump_parameter_value(pv,'sigma')
        sigma  = vsini /1.31 # assume sigma is vsini/1.31 (see Hirano et al. 2010, 2011)
        secosw =self.get_jump_parameter_value(pv,'secosw_p1')
        sesinw =self.get_jump_parameter_value(pv,'sesinw_p1')
        # Perform parameter transformations
        e      =np.sqrt(secosw**2. + sesinw**2.)
        omega  =np.arctan2(sesinw,secosw)
        aRs    =aRs_from_Tdur_Tfull(Tdur, Tfull, rprs, P, e=e, omega=omega)
        b      =b_from_Tdur_Tfull(Tdur, Tfull, rprs)
        ii     =np.rad2deg(np.arccos(b / aRs))
        # e      =self.get_jump_parameter_value(pv,'ecc_p1')
        # omega  =self.get_jump_parameter_value(pv,'omega_p1')
        exptime=self.get_jump_parameter_value(pv,'exptime')/86400. # exptime in days
        if times is None:
            times = self.data["x"]
        self.RH = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime,limb_dark='quadratic')
        self.rm = self.RH.evaluate(times)
        return self.rm

    def compute_cb_model(self,pv,times=None):
        """
        Compute convective blueshift model

        NOTES:
            See Shporer & Brown 2011
        """
        ################
        # adding v_cb
        if times is None:
            times = self.data["x"]
        vcb    =self.get_jump_parameter_value(pv,'vcb')
        if vcb!=0:
            T0     =self.get_jump_parameter_value(pv,'t0_p1')
            P      =self.get_jump_parameter_value(pv,'P_p1')
            # ii     =self.get_jump_parameter_value(pv,'inc_p1')
            rprs   =self.get_jump_parameter_value(pv,'p_p1')
            # aRs    =self.get_jump_parameter_value(pv,'a_p1')
            u1     =self.get_jump_parameter_value(pv,'u1')
            u2     =self.get_jump_parameter_value(pv,'u2')
            secosw =self.get_jump_parameter_value(pv,'secosw_p1')
            sesinw =self.get_jump_parameter_value(pv,'sesinw_p1')
            # Perform parameter transformations
            e      =np.sqrt(secosw**2. + sesinw**2.)
            omega  =np.arctan2(sesinw,secosw)
            aRs    =aRs_from_Tdur_Tfull(Tdur, Tfull, rprs, P, e=e, omega=omega)
            b      =b_from_Tdur_Tfull(Tdur, Tfull, rprs)
            ii     =np.rad2deg(np.arccos(b / aRs))
            # e      =self.get_jump_parameter_value(pv,'ecc_p1')
            # omega  =self.get_jump_parameter_value(pv,'omega_p1')

            # Calculate separation of centers
            x_1, y_1, z_1 = planet_XYZ_position(times,T0,P,aRs,ii,e,omega)
            ds = np.sqrt(x_1**2.+y_1**2.)

            self.vels_cb = convective_blueshift.cb_limbdark(ds,rprs,u1,u2,vcb,epsabs=1.49e-1,epsrel=1.49e-1)
            return self.vels_cb
        else:
            return np.zeros(len(times))
        ################
        
    def compute_rv_model(self,pv,times=None):
        """
        Compute the RV model

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rv - the rv model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]
        T0      = self.get_jump_parameter_value(pv,'t0_p1')
        P       = self.get_jump_parameter_value(pv,'P_p1')
        gamma   = self.get_jump_parameter_value(pv,'gamma')
        K       = self.get_jump_parameter_value(pv,'K_p1')
        secosw  =self.get_jump_parameter_value(pv,'secosw_p1')
        sesinw  =self.get_jump_parameter_value(pv,'sesinw_p1')
        e       =np.sqrt(secosw**2. + sesinw**2.)
        omega   =np.arctan2(sesinw,secosw)
        # e       = self.get_jump_parameter_value(pv,'ecc_p1')
        # w       = self.get_jump_parameter_value(pv,'omega_p1')
        self.rv = get_rv_curve(times,P=P,tc=T0,e=e,omega=omega,K=K)+gamma
        return self.rv

    def compute_polynomial_model(self,pv,times=None):
        """
        Compute the polynomial model.  Note that if gammadot and gammadotdot
        are not specified in the priors file, they both default to zero.

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            poly - the polynomial model evaluated at 'times' if supplied,
                   otherwise defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]

        #T0 = self.get_jump_parameter_value(pv,'t0_p1')
        # Use Mean of data instead
        T0 = (self.data['x'][0] + self.data['x'][-1])/2.
        try:
            gammadot = self.get_jump_parameter_value(pv,'gammadot')
        except KeyError as e:
            gammadot = 0
        try:
            gammadotdot = self.get_jump_parameter_value(pv,'gammadotdot')
        except KeyError as e:
            gammadotdot = 0

        self.poly = (
            gammadot * (times - T0) +
            gammadotdot * (times - T0)**2
        )
        return self.poly

    def compute_total_model(self,pv,times=None):
        """
        Computes the full RM model (including RM and RV and CB)

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rm - the rm model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps

        NOTES:
            see compute_rm_model(), compute_rv_model(),
            compute_polynomial_model()
        """
        return (
            self.compute_rm_model(pv,times=times) +
            self.compute_rv_model(pv,times=times) +
            self.compute_polynomial_model(pv,times=times) +
            self.compute_cb_model(pv,times=times)
        )

    def __call__(self,pv):
        """
        Return the log likelihood

        INPUT:
            pv - the input list of varying parameters
        """
        if any(pv < self.ps_vary.pmins) or any(pv>self.ps_vary.pmaxs):
            return -np.inf

        # ii =self.get_jump_parameter_value(pv,'inc_p1')
        # if ii > 90:
        #     return -np.inf

        ###############
        # Prepare data and model and error for ingestion into likelihood
        y_data = self.data['y']
        y_model = self.compute_total_model(pv)
        # jitter in quadrature
        jitter = self.get_jump_parameter_value(pv,'sigma_rv')
        error = np.sqrt(self.data['error']**2.+jitter**2.)
        ###############

        # Return the log-likelihood
        log_of_priors = self.ps_vary.c_log_prior(pv)
        # Calculate log likelihood
        log_of_model  = ll_normal_ev_py(y_data, y_model, error)
        log_ln = log_of_priors + log_of_model
        if np.isnan(log_ln):
            return -np.inf
        return log_ln


class LPFunctionTransObsIStar(object):
    """
    Log-Likelihood function class

    Parameterizes in terms of transit observables:
    - Tdur: Transit duration (first to fourth contacts)
    - Tfull: Duration of full transit (second to third contacts)

    NOTES:
        Based on hpprvi's class, see: https://github.com/hpparvi/exo_tutorials
    """
    def __init__(self,x,y,yerr,file_priors):
        """
        INPUT:
            x - time values in BJD
            y - y values in m/s
            yerr - yerr values in m/s
            file_priors - prior file name
        """
        self.data= {"x"   : x,
                    "y"   : y,
                    "error"  : yerr}
        # Setting priors
        self.ps_all = priorset_from_file(file_priors) # all priors
        self.ps_fixed = PriorSet(np.array(self.ps_all.priors)[np.array(self.ps_all.fixed)]) # fixed priorset
        self.ps_vary  = PriorSet(np.array(self.ps_all.priors)[~np.array(self.ps_all.fixed)]) # varying priorset
        self.ps_fixed_dict = {key: val for key, val in zip(self.ps_fixed.labels,self.ps_fixed.args1)}
        print('Reading in priorfile from {}'.format(file_priors))
        print(self.ps_all.df)

    def get_jump_parameter_index(self,lab):
        """
        Get the index of a given label
        """
        return np.where(np.array(self.ps_vary.labels)==lab)[0][0]

    def get_jump_parameter_value(self,pv,lab):
        """
        Get the current value in the argument list 'pv' that has label 'lab'
        """
        # First check if we are actually varying it
        if lab in self.ps_vary.labels:
            return pv[self.get_jump_parameter_index(lab)]
        else:
            # We are not varying it
            return self.ps_fixed_dict[lab]

    def compute_rm_model(self,pv,times=None):
        """
        Calls RM model and returns the transit model

        INPUT:
            pv    - parameters passed to the function
            times - times, and array of timestamps

        OUTPUT:
            lc - the lightcurve model at *times*
        """
        T0     =self.get_jump_parameter_value(pv,'t0_p1')
        P      =self.get_jump_parameter_value(pv,'P_p1')
        lam    =self.get_jump_parameter_value(pv,'lam_p1')
        cosi    = self.get_jump_parameter_value(pv,'cosi')
        R       = self.get_jump_parameter_value(pv,'rstar')
        Prot    = self.get_jump_parameter_value(pv,'Prot')
        veq = (2.*np.pi*R*aconst.R_sun.value)/(Prot*86400.*1000.) # km/s
        vsini   = veq*np.sqrt(1.-cosi**2.)
        # vsini  =self.get_jump_parameter_value(pv,'vsini')
        rprs   =self.get_jump_parameter_value(pv,'p_p1')
        # ii     =self.get_jump_parameter_value(pv,'inc_p1')
        # aRs    =self.get_jump_parameter_value(pv,'a_p1')
        # Tdur and tau replace a/Rstar and inclination
        Tdur   =self.get_jump_parameter_value(pv,'Tdur_p1')
        Tfull  =self.get_jump_parameter_value(pv,'Tfull_p1')
        # tau    =self.get_jump_parameter_value(pv,'tau_p1')
        u1     =self.get_jump_parameter_value(pv,'u1')
        u2     =self.get_jump_parameter_value(pv,'u2')
        gamma  =self.get_jump_parameter_value(pv,'gamma')
        beta   =self.get_jump_parameter_value(pv,'vbeta')
        #sigma  =self.get_jump_parameter_value(pv,'sigma')
        sigma  = vsini /1.31 # assume sigma is vsini/1.31 (see Hirano et al. 2010, 2011)
        secosw =self.get_jump_parameter_value(pv,'secosw_p1')
        sesinw =self.get_jump_parameter_value(pv,'sesinw_p1')
        # Perform parameter transformations
        e      =np.sqrt(secosw**2. + sesinw**2.)
        omega  =np.arctan2(sesinw,secosw)
        aRs    =aRs_from_Tdur_Tfull(Tdur, Tfull, rprs, P, e=e, omega=omega)
        b      =b_from_Tdur_Tfull(Tdur, Tfull, rprs)
        ii     =np.rad2deg(np.arccos(b / aRs))
        # e      =self.get_jump_parameter_value(pv,'ecc_p1')
        # omega  =self.get_jump_parameter_value(pv,'omega_p1')
        exptime=self.get_jump_parameter_value(pv,'exptime')/86400. # exptime in days
        if times is None:
            times = self.data["x"]
        self.RH = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime,limb_dark='quadratic')
        self.rm = self.RH.evaluate(times)
        return self.rm

    def compute_cb_model(self,pv,times=None):
        """
        Compute convective blueshift model

        NOTES:
            See Shporer & Brown 2011
        """
        ################
        # adding v_cb
        if times is None:
            times = self.data["x"]
        vcb    =self.get_jump_parameter_value(pv,'vcb')
        if vcb!=0:
            T0     =self.get_jump_parameter_value(pv,'t0_p1')
            P      =self.get_jump_parameter_value(pv,'P_p1')
            # ii     =self.get_jump_parameter_value(pv,'inc_p1')
            rprs   =self.get_jump_parameter_value(pv,'p_p1')
            # aRs    =self.get_jump_parameter_value(pv,'a_p1')
            u1     =self.get_jump_parameter_value(pv,'u1')
            u2     =self.get_jump_parameter_value(pv,'u2')
            secosw =self.get_jump_parameter_value(pv,'secosw_p1')
            sesinw =self.get_jump_parameter_value(pv,'sesinw_p1')
            # Perform parameter transformations
            e      =np.sqrt(secosw**2. + sesinw**2.)
            omega  =np.arctan2(sesinw,secosw)
            aRs    =aRs_from_Tdur_Tfull(Tdur, Tfull, rprs, P, e=e, omega=omega)
            b      =b_from_Tdur_Tfull(Tdur, Tfull, rprs)
            ii     =np.rad2deg(np.arccos(b / aRs))
            # e      =self.get_jump_parameter_value(pv,'ecc_p1')
            # omega  =self.get_jump_parameter_value(pv,'omega_p1')

            # Calculate separation of centers
            x_1, y_1, z_1 = planet_XYZ_position(times,T0,P,aRs,ii,e,omega)
            ds = np.sqrt(x_1**2.+y_1**2.)

            self.vels_cb = convective_blueshift.cb_limbdark(ds,rprs,u1,u2,vcb,epsabs=1.49e-1,epsrel=1.49e-1)
            return self.vels_cb
        else:
            return np.zeros(len(times))
        ################
        
    def compute_rv_model(self,pv,times=None):
        """
        Compute the RV model

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rv - the rv model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]
        T0      = self.get_jump_parameter_value(pv,'t0_p1')
        P       = self.get_jump_parameter_value(pv,'P_p1')
        gamma   = self.get_jump_parameter_value(pv,'gamma')
        K       = self.get_jump_parameter_value(pv,'K_p1')
        secosw  =self.get_jump_parameter_value(pv,'secosw_p1')
        sesinw  =self.get_jump_parameter_value(pv,'sesinw_p1')
        e       =np.sqrt(secosw**2. + sesinw**2.)
        omega   =np.arctan2(sesinw,secosw)
        # e       = self.get_jump_parameter_value(pv,'ecc_p1')
        # w       = self.get_jump_parameter_value(pv,'omega_p1')
        self.rv = get_rv_curve(times,P=P,tc=T0,e=e,omega=omega,K=K)+gamma
        return self.rv

    def compute_polynomial_model(self,pv,times=None):
        """
        Compute the polynomial model.  Note that if gammadot and gammadotdot
        are not specified in the priors file, they both default to zero.

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            poly - the polynomial model evaluated at 'times' if supplied,
                   otherwise defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]

        #T0 = self.get_jump_parameter_value(pv,'t0_p1')
        # Use Mean of data instead
        T0 = (self.data['x'][0] + self.data['x'][-1])/2.
        try:
            gammadot = self.get_jump_parameter_value(pv,'gammadot')
        except KeyError as e:
            gammadot = 0
        try:
            gammadotdot = self.get_jump_parameter_value(pv,'gammadotdot')
        except KeyError as e:
            gammadotdot = 0

        self.poly = (
            gammadot * (times - T0) +
            gammadotdot * (times - T0)**2
        )
        return self.poly

    def compute_total_model(self,pv,times=None):
        """
        Computes the full RM model (including RM and RV and CB)

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rm - the rm model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps

        NOTES:
            see compute_rm_model(), compute_rv_model(),
            compute_polynomial_model()
        """
        return (
            self.compute_rm_model(pv,times=times) +
            self.compute_rv_model(pv,times=times) +
            self.compute_polynomial_model(pv,times=times) +
            self.compute_cb_model(pv,times=times)
        )

    def __call__(self,pv):
        """
        Return the log likelihood

        INPUT:
            pv - the input list of varying parameters
        """
        if any(pv < self.ps_vary.pmins) or any(pv>self.ps_vary.pmaxs):
            return -np.inf

        # ii =self.get_jump_parameter_value(pv,'inc_p1')
        # if ii > 90:
        #     return -np.inf

        ###############
        # Prepare data and model and error for ingestion into likelihood
        y_data = self.data['y']
        y_model = self.compute_total_model(pv)
        # jitter in quadrature
        jitter = self.get_jump_parameter_value(pv,'sigma_rv')
        error = np.sqrt(self.data['error']**2.+jitter**2.)
        ###############

        # Return the log-likelihood
        log_of_priors = self.ps_vary.c_log_prior(pv)
        # Calculate log likelihood
        log_of_model  = ll_normal_ev_py(y_data, y_model, error)
        log_ln = log_of_priors + log_of_model
        if np.isnan(log_ln):
            return -np.inf
        return log_ln


class LPFunction(object):
    """
    Log-Likelihood function class

    NOTES:
        Based on hpprvi's class, see: https://github.com/hpparvi/exo_tutorials
    """
    def __init__(self,x,y,yerr,file_priors):
        """
        INPUT:
            x - time values in BJD
            y - y values in m/s
            yerr - yerr values in m/s
            file_priors - prior file name
        """
        self.data= {"x"   : x,
                    "y"   : y,
                    "error"  : yerr}
        # Setting priors
        self.ps_all = priorset_from_file(file_priors) # all priors
        self.ps_fixed = PriorSet(np.array(self.ps_all.priors)[np.array(self.ps_all.fixed)]) # fixed priorset
        self.ps_vary  = PriorSet(np.array(self.ps_all.priors)[~np.array(self.ps_all.fixed)]) # varying priorset
        self.ps_fixed_dict = {key: val for key, val in zip(self.ps_fixed.labels,self.ps_fixed.args1)}
        print('Reading in priorfile from {}'.format(file_priors))
        print(self.ps_all.df)

    def get_jump_parameter_index(self,lab):
        """
        Get the index of a given label
        """
        return np.where(np.array(self.ps_vary.labels)==lab)[0][0]

    def get_jump_parameter_value(self,pv,lab):
        """
        Get the current value in the argument list 'pv' that has label 'lab'
        """
        # First check if we are actually varying it
        if lab in self.ps_vary.labels:
            return pv[self.get_jump_parameter_index(lab)]
        else:
            # We are not varying it
            return self.ps_fixed_dict[lab]

    def compute_rm_model(self,pv,times=None):
        """
        Calls RM model and returns the transit model

        INPUT:
            pv    - parameters passed to the function
            times - times, and array of timestamps

        OUTPUT:
            lc - the lightcurve model at *times*
        """
        T0     =self.get_jump_parameter_value(pv,'t0_p1')
        P      =self.get_jump_parameter_value(pv,'P_p1')
        lam    =self.get_jump_parameter_value(pv,'lam_p1')
        vsini  =self.get_jump_parameter_value(pv,'vsini')
        ii     =self.get_jump_parameter_value(pv,'inc_p1')
        rprs   =self.get_jump_parameter_value(pv,'p_p1')
        aRs    =self.get_jump_parameter_value(pv,'a_p1')
        u1     =self.get_jump_parameter_value(pv,'u1')
        u2     =self.get_jump_parameter_value(pv,'u2')
        gamma  =self.get_jump_parameter_value(pv,'gamma')
        beta   =self.get_jump_parameter_value(pv,'vbeta')
        #sigma  =self.get_jump_parameter_value(pv,'sigma')
        sigma  = vsini /1.31 # assume sigma is vsini/1.31 (see Hirano et al. 2010, 2011)
        e      =self.get_jump_parameter_value(pv,'ecc_p1')
        omega  =self.get_jump_parameter_value(pv,'omega_p1')
        exptime=self.get_jump_parameter_value(pv,'exptime')/86400. # exptime in days
        if times is None:
            times = self.data["x"]
        self.RH = RMHirano(lam,vsini,P,T0,aRs,ii,rprs,e,omega,[u1,u2],beta,
                            sigma,supersample_factor=7,exp_time=exptime,limb_dark='quadratic')
        self.rm = self.RH.evaluate(times)
        return self.rm

    def compute_cb_model(self,pv,times=None):
        """
        Compute convective blueshift model

        NOTES:
            See Shporer & Brown 2011
        """
        ################
        # adding v_cb
        if times is None:
            times = self.data["x"]
        vcb    =self.get_jump_parameter_value(pv,'vcb')
        if vcb!=0:
            T0     =self.get_jump_parameter_value(pv,'t0_p1')
            P      =self.get_jump_parameter_value(pv,'P_p1')
            ii     =self.get_jump_parameter_value(pv,'inc_p1')
            rprs   =self.get_jump_parameter_value(pv,'p_p1')
            aRs    =self.get_jump_parameter_value(pv,'a_p1')
            u1     =self.get_jump_parameter_value(pv,'u1')
            u2     =self.get_jump_parameter_value(pv,'u2')
            e      =self.get_jump_parameter_value(pv,'ecc_p1')
            omega  =self.get_jump_parameter_value(pv,'omega_p1')

            # Calculate separation of centers
            x_1, y_1, z_1 = planet_XYZ_position(times,T0,P,aRs,ii,e,omega)
            ds = np.sqrt(x_1**2.+y_1**2.)

            self.vels_cb = convective_blueshift.cb_limbdark(ds,rprs,u1,u2,vcb,epsabs=1.49e-1,epsrel=1.49e-1)
            return self.vels_cb
        else:
            return np.zeros(len(times))
        ################
        
    def compute_rv_model(self,pv,times=None):
        """
        Compute the RV model

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rv - the rv model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]
        T0      = self.get_jump_parameter_value(pv,'t0_p1')
        P       = self.get_jump_parameter_value(pv,'P_p1')
        gamma   = self.get_jump_parameter_value(pv,'gamma')
        K       = self.get_jump_parameter_value(pv,'K_p1')
        e       = self.get_jump_parameter_value(pv,'ecc_p1')
        w       = self.get_jump_parameter_value(pv,'omega_p1')
        self.rv = get_rv_curve(times,P=P,tc=T0,e=e,omega=w,K=K)+gamma
        return self.rv

    def compute_polynomial_model(self,pv,times=None):
        """
        Compute the polynomial model.  Note that if gammadot and gammadotdot
        are not specified in the priors file, they both default to zero.

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            poly - the polynomial model evaluated at 'times' if supplied,
                   otherwise defaults to original data timestamps
        """
        if times is None:
            times = self.data["x"]

        #T0 = self.get_jump_parameter_value(pv,'t0_p1')
        # Use Mean of data instead
        T0 = (self.data['x'][0] + self.data['x'][-1])/2.
        try:
            gammadot = self.get_jump_parameter_value(pv,'gammadot')
        except KeyError as e:
            gammadot = 0
        try:
            gammadotdot = self.get_jump_parameter_value(pv,'gammadotdot')
        except KeyError as e:
            gammadotdot = 0

        self.poly = (
            gammadot * (times - T0) +
            gammadotdot * (times - T0)**2
        )
        return self.poly

    def compute_total_model(self,pv,times=None):
        """
        Computes the full RM model (including RM and RV and CB)

        INPUT:
            pv    - a list of parameters (only parameters that are being varied)
            times - times (optional), array of timestamps

        OUTPUT:
            rm - the rm model evaluated at 'times' if supplied, otherwise
                      defaults to original data timestamps

        NOTES:
            see compute_rm_model(), compute_rv_model(),
            compute_polynomial_model()
        """
        return (
            self.compute_rm_model(pv,times=times) +
            self.compute_rv_model(pv,times=times) +
            self.compute_polynomial_model(pv,times=times) +
            self.compute_cb_model(pv,times=times)
        )

    def __call__(self,pv):
        """
        Return the log likelihood

        INPUT:
            pv - the input list of varying parameters
        """
        if any(pv < self.ps_vary.pmins) or any(pv>self.ps_vary.pmaxs):
            return -np.inf

        ii =self.get_jump_parameter_value(pv,'inc_p1')
        if ii > 90:
            return -np.inf

        ###############
        # Prepare data and model and error for ingestion into likelihood
        y_data = self.data['y']
        y_model = self.compute_total_model(pv)
        # jitter in quadrature
        jitter = self.get_jump_parameter_value(pv,'sigma_rv')
        error = np.sqrt(self.data['error']**2.+jitter**2.)
        ###############

        # Return the log-likelihood
        log_of_priors = self.ps_vary.c_log_prior(pv)
        # Calculate log likelihood
        log_of_model  = ll_normal_ev_py(y_data, y_model, error)
        log_ln = log_of_priors + log_of_model
        return log_ln

class RMFit(object):
    """
    A class that does RM fitting.

    NOTES:
        - Needs to have LPFunction defined
    """
    def __init__(self,LPFunction):
        self.lpf = LPFunction
        self.de = None

    def minimize_AMOEBA(self):
        centers = np.array(self.lpf.ps_vary.centers)

        def neg_lpf(pv):
            return -1.*self.lpf(pv)
        self.min_pv = minimize(neg_lpf,centers,method='Nelder-Mead',tol=1e-9,
                                   options={'maxiter': 100000, 'maxfev': 10000, 'disp': True}).x

    def minimize_PyDE(self, npop=100, de_iter=200, de_c=0.5, maximize=True, force_de=False,
                      mcmc=True, mc_iter=1000, mc_thin=1, nthreads=8, 
                      plot_priors=True,sample_ball=False,k=None,n=None,
                      mc_outfile=None, mc_reset=True):
        """
        Minimize using the PyDE

        NOTES:
            see https://github.com/hpparvi/PyDE
        """
        centers = np.array(self.lpf.ps_vary.centers)
        if self.de is None or force_de:
            print("Running PyDE Optimizer")
            self.de = pyde.de.DiffEvol(self.lpf, self.lpf.ps_vary.bounds, npop, c=de_c, maximize=maximize) # we want to maximize the likelihood
            self.min_pv, self.min_pv_lnval = self.de.optimize(ngen=de_iter)
            print("Optimized using PyDE")
            print("Final parameters:")
            self.print_param_diagnostics(self.min_pv)
            #self.lpf.ps.plot_all(figsize=(6,4),pv=self.min_pv)
            print("LogPost value:",-1*self.min_pv_lnval)
            self.lnl_max  = -1*self.min_pv_lnval-self.lpf.ps_vary.c_log_prior(self.min_pv)
            print("LnL value:",self.lnl_max)
            print("Log priors",self.lpf.ps_vary.c_log_prior(self.min_pv))
            if k is not None and n is not None:
                print("BIC:",stats_help.bic_from_likelihood(self.lnl_max,k,n))
                print("AIC:",stats_help.aic(k,self.lnl_max))
        if mcmc:
            print("Running MCMC with {:d} iterations, thinning = {:d}".format(mc_iter,mc_thin))
            resume = False
            if mc_outfile is not None:
                print("Saving samples to {:s}".format(mc_outfile))
                backend = emcee.backends.HDFBackend(mc_outfile)
                if mc_reset or not os.path.exists(mc_outfile):
                    backend.reset(nwalkers=npop, ndim=self.lpf.ps_vary.ndim)
                else:
                    print("Resuming MCMC, starting from iteration {:d}".format(backend.iteration))
                    resume = True
            else:
                backend = None
            with Pool(nthreads) as pool:
                self.sampler = emcee.EnsembleSampler(npop, self.lpf.ps_vary.ndim, self.lpf, backend=backend, pool=pool)

                old_tau = np.inf
                start_pop = None if resume else self.de.population
                for sample in self.sampler.sample(start_pop, iterations=mc_iter, thin_by=mc_thin, progress=True):
                    # Only check for convergence every 100 steps, starting at 10%.
                    if (self.sampler.iteration % 100) or (self.sampler.iteration < (mc_iter // 10)):
                        continue
                    tau = self.sampler.get_autocorr_time(tol=0, quiet=True)
                    print('Autocorrelation time: Max = {:.0f}, Mean = {:.0f}'.format(np.max(tau), np.mean(tau)))
                    print('Mean acceptance fraction: {:.3f}'.format(np.mean(self.sampler.acceptance_fraction)))
                    # Check convergence: 100 autocorrelation times + max relative change of < 1%.
                    converged = np.all(tau * 100 < self.sampler.iteration)
                    converged &= np.all(np.abs(old_tau - tau) / tau < 0.01)
                    if converged:
                        break
                    old_tau = tau

            print("Finished MCMC")
            tau = np.max(self.sampler.get_autocorr_time(quiet=True))
            print("Max autocorrelation time: {:.0f} steps".format(tau))
            if self.sampler.iteration < (100 * tau):
                print("Warning: number of iterations {:d} is less than 100 times the autocorrelation time {:.0f}".format(self.sampler.iteration, tau))
            else:
                print("MCMC converged, number of iterations {:d} is {:.0f} times the autocorrelation time {:.0f}".format(self.sampler.iteration, self.sampler.iteration / tau, tau))

            print("Mean acceptance fraction: {:.3f}".format(np.mean(self.sampler.acceptance_fraction)))
            log_probs = self.sampler.get_log_prob()
            max_log_prob = np.max(log_probs)
            print("Max LogPost: {:.3f}".format(max_log_prob))
            try:
                k = self.lpf.n_vary
                n = self.lpf.n_data
                print("Number of parameters: {:d}".format(k))
                print("Number of data points: {:d}".format(n))
                print("BIC: {:.3f}".format(stats_help.bic_from_likelihood(max_log_prob,k,n)))
                print("AIC: {:.3f}".format(stats_help.aic(k,max_log_prob)))
            except:
                pass
            self.min_pv_mcmc = self.get_mean_values_mcmc_posteriors().medvals.values

    def get_mean_values_mcmc_posteriors(self,flatchain=None):
        """
        Get the mean values from the posteriors

            flatchain - if not passed, then will default using the full flatchain (will likely include burnin)

        EXAMPLE:
        """
        if flatchain is None:
            flatchain = self.sampler.flatchain
            print('No flatchain passed, defaulting to using full chains')
        df_list = [utils.get_mean_values_for_posterior(flatchain[:,i],label,description) for i,label,description in zip(range(len(self.lpf.ps_vary.descriptions)),self.lpf.ps_vary.labels,self.lpf.ps_vary.descriptions)]
        return pd.concat(df_list)

    def print_param_diagnostics(self,pv):
        """
        A function to print nice parameter diagnostics.
        """
        self.df_diagnostics = pd.DataFrame(zip(self.lpf.ps_vary.labels,self.lpf.ps_vary.centers,self.lpf.ps_vary.bounds[:,0],self.lpf.ps_vary.bounds[:,1],pv,self.lpf.ps_vary.centers-pv),columns=["labels","centers","lower","upper","pv","center_dist"])
        print(self.df_diagnostics.to_string(float_format='%.6f'))
        return self.df_diagnostics

    def plot_fit(self,pv=None,times=None):
        """
        Plot the model curve for a given set of parameters pv

        INPUT:
            pv - an array containing a sample draw of the parameters defined in self.lpf.ps_vary
               - will default to best-fit parameters if none are supplied
        """
        if pv is None:
            print('Plotting curve with best-fit values')
            pv = self.min_pv
        x = self.lpf.data['x']
        y = self.lpf.data['y']
        jitter = self.lpf.get_jump_parameter_value(pv,'sigma_rv')
        yerr = np.sqrt(self.lpf.data['error']**2.+jitter**2.)
        model_obs = self.lpf.compute_total_model(pv)
        residuals = y-model_obs
            
        model = self.lpf.compute_total_model(pv)
        residuals = y-model

        # Plot
        nrows = 2
        self.fig, self.ax = plt.subplots(nrows=nrows,sharex=True,figsize=(10,6),gridspec_kw={'height_ratios': [5, 2]})
        self.ax[0].errorbar(x,y,yerr=yerr,elinewidth=1,lw=0,alpha=1,capsize=5,mew=1,marker="o",barsabove=True,markersize=8,label="Data")
        if times is not None:
            model = self.lpf.compute_total_model(pv,times=times)
            self.ax[0].plot(times,model,label="Model",color='crimson')
        else:
            self.ax[0].plot(x,model_obs,label="Model",color='crimson')
            
        self.ax[1].errorbar(x,residuals,yerr=yerr,elinewidth=1,lw=0,alpha=1,capsize=5,mew=1,marker="o",barsabove=True,markersize=8,
                            label="Residuals, std="+str(np.std(residuals)))
        for xx in self.ax:
            xx.minorticks_on()
            xx.legend(loc='lower left',fontsize=9)
            xx.set_ylabel("RV [m/s]",labelpad=2)
        self.ax[-1].set_xlabel("Time (BJD)",labelpad=2)
        self.ax[0].set_title("RM Effect")
        self.fig.subplots_adjust(wspace=0.05,hspace=0.05)

    def plot_mcmc_fit(self,times=None):
        df = self.get_mean_values_mcmc_posteriors()
        print('Plotting curve with best-fit mcmc values')
        self.plot_fit(pv=df.medvals.values)

def read_priors(priorname):
    """
    Read a prior file as in juliet.py style

    OUTPUT:
        priors - prior dictionary
        n_params - number of parameters

    EXAMPLE:
        P, numpriors = read_priors('../data/priors.dat')
    """
    fin = open(priorname)
    priors = {}
    n_transit = 0
    n_rv = 0
    n_params = 0
    numbering_transit = np.array([])
    numbering_rv = np.array([])
    while True:
        line = fin.readline()
        if line != '':
            if line[0] != '#':
                line = line.split('#')[0] # remove things after comment
                out = line.split()
                parameter,prior_name,vals = out
                parameter = parameter.split()[0]
                prior_name = prior_name.split()[0]
                vals = vals.split()[0]
                priors[parameter] = {}
                pvector = parameter.split('_')
                # Check if parameter/planet is from a transiting planet:
                if pvector[0] == 'r1' or pvector[0] == 'p':
                    pnumber = int(pvector[1][1:])
                    numbering_transit = np.append(numbering_transit,pnumber)
                    n_transit += 1
                # Check if parameter/planet is from a RV planet:
                if pvector[0] == 'K':
                    pnumber = int(pvector[1][1:])
                    numbering_rv = np.append(numbering_rv,pnumber)
                    n_rv += 1
                if prior_name.lower() == 'fixed':
                    priors[parameter]['type'] = prior_name.lower()
                    priors[parameter]['value'] = np.double(vals)
                    priors[parameter]['cvalue'] = np.double(vals)
                else:
                    n_params += 1
                    priors[parameter]['type'] = prior_name.lower()
                    if priors[parameter]['type'] != 'truncatednormal':
                        v1,v2 = vals.split(',')
                        priors[parameter]['value'] = [np.double(v1),np.double(v2)]
                    else:
                        v1,v2,v3,v4 = vals.split(',')
                        priors[parameter]['value'] = [np.double(v1),np.double(v2),np.double(v3),np.double(v4)]
                    priors[parameter]['cvalue'] = 0.
        else:
            break
    #return priors, n_transit, n_rv, numbering_transit.astype('int'), numbering_rv.astype('int'), n_params
    return priors, n_params

def priordict_to_priorset(priordict,verbose=True):
    """
    Get a PriorSet from prior diectionary

    EXAMPLE:
        P, numpriors = readpriors('../data/priors.dat')
        ps = priordict_to_priorset(priors)
        ps.df
    """
    priors = []
    for key in priordict.keys():
        inp = priordict[key]
        if verbose: print(key)
        val = inp['value']
        if inp['type'] == 'normal':
            outp = NP(val[0],val[1],key,key,priortype='model')
        elif inp['type'] == 'truncatednormal':
            outp = NP(val[0],val[1],key,key,priortype='model',lims=(val[2],val[3]))
        elif inp['type'] == 'uniform':
            outp = UP(val[0],val[1],key,key,priortype='model')
        elif inp['type'] == 'fixed':
            outp = FP(val,key,key,priortype='model')
        else:
            print('Error, ptype {} not supported'.format(inp['type']))
        priors.append(outp)
    return PriorSet(priors)

def priorset_from_file(filename,verbose=False):
    """
    Get a PriorSet() from a filename
    """
    priordict, num_priors = read_priors(filename)
    return priordict_to_priorset(priordict,verbose)

class RMHirano(object):
    def __init__(self,lam,vsini,P,T0,aRs,i,RpRs,e,w,u,beta,sigma,supersample_factor=7,exp_time=0.00035,limb_dark='linear'):
        """
        Evaluate Rossiter McLaughlin effect using the model of Hirano et al. 2010, 2011

        INPUT:
            lam - sky-projected obliquity in deg
            vsini - sky-projected rotational velocity in km/s
            P - Period in days
            T0 - Transit center
            aRs - a/R*
            i - inclination in degrees
            RpRs - radius ratio
            e - eccentricity
            w - omega in degrees
            u - [u1,u2] where u1 and u2 are the quadratic limb-dark coefficients
            beta - Gaussian dispersion of spectral lines, in km/s, typically 2.5-4.5km/s (see Hirano+11)
            sigma - Gaussian broadening kernel from Hirano+10. Hirano+10 found vsini/1.31 as an approximation that sometimes works (Why?).

        EXAMPLE:
            times = np.linspace(-0.05,0.05,200)
            T0 = 0.
            P = 3.48456408
            aRs = 21.09
            i = 89.
            vsini = 8.7
            rprs = np.sqrt(0.01)
            e = 0.
            w = 90.
            lam = 45.
            u = [0.3,0.3]
            R = RMHirano(lam,vsini,P,T0,aRs,i,rprs,e,w,u,limb_dark='quadratic')
            rm = R.evaluate(times)

            fig, ax = plt.subplots()
            ax.plot(times,rm)
        """
        self.lam = lam
        self.vsini = vsini
        self.P = P
        self.T0 = T0
        self.aRs = aRs
        self.i = i
        self.iS = 90. # not really using anymore, as it cancels out, should just remove
        self.RpRs = RpRs
        self.e = e
        self.w = w
        self.u = u
        self.limb_dark = limb_dark
        self.rstar = 1. # not really using anymore, as it cancels out, should just remove
        self.beta = beta
        self.sigma = sigma
        self.exp_time = exp_time
        self.supersample_factor = int(supersample_factor)
        # self._Omega = (self.vsini/np.sin(np.deg2rad(self.iS)))/(self.rstar*aconst.R_sun.value/1000.)

    def true_anomaly(self,times):
        """
        Calculate the true anomaly
        """
        f = true_anomaly(times,self.T0,self.P,self.aRs,self.i,self.e,self.w)
        return f

    def calc_transit(self,times):
        """
        Calculate transit model of planet
        """
        params = batman.TransitParams()
        params.t0 = self.T0
        params.per = self.P
        params.inc = self.i
        params.rp = self.RpRs
        params.a = self.aRs
        params.ecc = self.e
        params.w = self.w
        params.u = self.u
        params.limb_dark = self.limb_dark
        params.fp = 0.001
        transitmodel = batman.TransitModel(params, times, transittype='primary',exp_time=self.exp_time,
                                         supersample_factor=self.supersample_factor)
        return transitmodel.light_curve(params)

    def planet_XYZ_position(self,times):
        """
        Get the planet XYZ position at times
        """
        X, Y, Z = planet_XYZ_position(times,self.T0,self.P,self.aRs,self.i,self.e,self.w)
        return X, Y, Z

    def Xp(self,times):
        lam, w, i = np.deg2rad(self.lam), np.deg2rad(self.w), np.deg2rad(self.i)
        f = self.true_anomaly(times)
        r = self.aRs*(1.-self.e**2.)/(1.+self.e*np.cos(f)) # distance
        x = -r*np.cos(f+w)*np.cos(lam) + r*np.sin(lam)*np.sin(f+w)*np.cos(i)
        return x

    def evaluate(self,times,base_error=0.):
        sigma = self.sigma
        beta = self.beta
        X = self.Xp(times)
        F = 1.-self.calc_transit(times)
        # vp = X*self._Omega*np.sin(np.deg2rad(self.iS))*self.rstar*aconst.R_sun.value/1000.
        vp = X * self.vsini
        v = -1000.*vp*F*((2.*beta**2.+2.*sigma**2)/(2.*beta**2+sigma**2))**(3./2.) * (1.-(vp**2.)/(2.*beta**2+sigma**2) + (vp**4.)/(2.*(2.*beta**2+sigma**2)**2.))
        # For diagnostics
        self.vp = vp
        self.X = X
        self.F = F
        if base_error >0:
            return v + np.random.normal(loc=0.,scale=base_error,size=len(v))
        else:
            return v

            
class RMHiranoDiffRot(RMHirano):
    """
    Evaluate Rossiter McLaughlin effect using the model of Hirano et al. 2010, 2011
    Accounts for differential rotation
    """
    def __init__(self,lam,vsini,P,T0,aRs,i,RpRs,e,w,u,beta,sigma,alpha,istar,supersample_factor=7,exp_time=0.00035,limb_dark='linear'):
        """
        Evaluate Rossiter McLaughlin effect using the model of Hirano et al. 2010, 2011

        INPUT:
            lam - sky-projected obliquity in deg
            vsini - sky-projected rotational velocity in km/s
            P - Period in days
            T0 - Transit center
            aRs - a/R*
            i - inclination in degrees
            RpRs - radius ratio
            e - eccentricity
            w - omega in degrees
            u - [u1,u2] where u1 and u2 are the quadratic limb-dark coefficients
            beta - Gaussian dispersion of spectral lines, in km/s, typically 2.5-4.5km/s (see Hirano+11)
            sigma - Gaussian broadening kernel from Hirano+10. Hirano+10 found vsini/1.31 as an approximation that sometimes works (Why?).

        EXAMPLE:
            times = np.linspace(-0.05,0.05,200)
            T0 = 0.
            P = 3.48456408
            aRs = 21.09
            i = 89.
            vsini = 8.7
            rprs = np.sqrt(0.01)
            e = 0.
            w = 90.
            lam = 45.
            u = [0.3,0.3]
            R = RMHirano(lam,vsini,P,T0,aRs,i,rprs,e,w,u,limb_dark='quadratic')
            rm = R.evaluate(times)

            fig, ax = plt.subplots()
            ax.plot(times,rm)
        """
        super().__init__(lam,vsini,P,T0,aRs,i,RpRs,e,w,u,beta,sigma,supersample_factor=supersample_factor,exp_time=exp_time,limb_dark=limb_dark)
        self.alpha = alpha
        self.iS = istar

    def calc_transit(self,times):
        """
        Calculate transit model of planet
        """
        params = batman.TransitParams()
        params.t0 = self.T0
        params.per = self.P
        params.inc = self.i
        params.rp = self.RpRs
        params.a = self.aRs
        params.ecc = self.e
        params.w = self.w
        params.u = self.u
        params.limb_dark = self.limb_dark
        params.fp = 0.001
        transitmodel = batman.TransitModel(params, times, transittype='primary',exp_time=self.exp_time / self.supersample_factor,
                                           supersample_factor=1)
        return transitmodel.light_curve(params)
        
    def XpYp(self,times):
        lam, w, i = np.deg2rad(self.lam), np.deg2rad(self.w), np.deg2rad(self.i)
        f = self.true_anomaly(times)
        r = self.aRs*(1.-self.e**2.)/(1.+self.e*np.cos(f)) # distance
        x = -r*np.cos(f+w)*np.cos(lam) + r*np.sin(lam)*np.sin(f+w)*np.cos(i)
        y = -r*np.cos(f+w)*np.sin(lam) - r*np.cos(lam)*np.sin(f+w)*np.cos(i)
        return x, y

    def evaluate(self,times,base_error=0.):
        if self.supersample_factor > 1:
            t_offsets = np.linspace(
                -self.exp_time / 2.0, self.exp_time / 2.0, self.supersample_factor
            )
            times_supersample = (t_offsets + times.reshape(times.size, 1)).flatten()
        else:
            times_supersample = times
        sigma = self.sigma
        beta = self.beta
        X, Y = self.XpYp(times_supersample)
        sin_lat = Y * np.sin(self.iS) + np.sqrt(np.clip(1 - X*X - Y*Y, 0.0, None)) * np.cos(self.iS)
        F = 1.-self.calc_transit(times_supersample)
        vp = X * self.vsini * (1 - self.alpha * sin_lat * sin_lat)
        # vp[np.abs(F) <= 1e-15] = 0.
        v = -1000.*vp*F*((2.*beta**2.+2.*sigma**2)/(2.*beta**2+sigma**2))**(3./2.) * (1.-(vp**2.)/(2.*beta**2+sigma**2) + (vp**4.)/(2.*(2.*beta**2+sigma**2)**2.))
        self.v = v
        v = np.mean(v.reshape(-1, self.supersample_factor), axis=1)
        # For diagnostics
        self.times_supersample = times_supersample
        self.vp = vp
        self.X = X
        self.F = F
        if base_error >0:
            return v + np.random.normal(loc=0.,scale=base_error,size=len(v))
        else:
            return v
    
# b(alpha) coefficients
bm1 = np.pi
b0 = 2
b1= 0.5 * bm1
b2 = 2/3 * b0
class RMBoue(object):
    def __init__(self,lam,vsini,P,T0,aRs,i,RpRs,e,w,u,beta,sigma,zeta=0.0,supersample_factor=7,exp_time=0.00035,limb_dark='linear'):
        """
        Evaluate Rossiter McLaughlin effect using the model of Hirano et al. 2010, 2011

        INPUT:
            lam - sky-projected obliquity in deg
            vsini - sky-projected rotational velocity in km/s
            P - Period in days
            T0 - Transit center
            aRs - a/R*
            i - inclination in degrees
            RpRs - radius ratio
            e - eccentricity
            w - omega in degrees
            u - [u1,u2] where u1 and u2 are the quadratic limb-dark coefficients
            beta - Width of subplanet line profile
            sigma - Width of Gaussian fit used to measure the CCFs
            zeta - Macroturbulent broadening

        EXAMPLE:
            times = np.linspace(-0.05,0.05,200)
            T0 = 0.
            P = 3.48456408
            aRs = 21.09
            i = 89.
            vsini = 8.7
            rprs = np.sqrt(0.01)
            e = 0.
            w = 90.
            lam = 45.
            u = [0.3,0.3]
            R = RMHirano(lam,vsini,P,T0,aRs,i,rprs,e,w,u,limb_dark='quadratic')
            rm = R.evaluate(times)

            fig, ax = plt.subplots()
            ax.plot(times,rm)
        """
        self.lam = lam
        self.vsini = vsini
        self.P = P
        self.T0 = T0
        self.aRs = aRs
        self.i = i
        self.iS = 90. # not really using anymore, as it cancels out, should just remove
        self.RpRs = RpRs
        self.e = e
        self.w = w
        self.u = u
        self.limb_dark = limb_dark
        self.beta = beta
        self.sigma = sigma
        self.zeta = zeta
        self.sigmat = np.sqrt(sigma**2 + beta**2 + (zeta**2)/2)
        self.exp_time = exp_time
        self.supersample_factor = int(supersample_factor)

        # Compute denominator
        self.a0 = self.boue_denominator()

    def boue_denominator(self):
        """
        Compute the denominator of the Boue+13 model
        """
        a0 = 4 * self.sigma * np.sqrt(np.pi) * quad(self.funcAmp_0, 0, 1)[0]
        return a0
        
    def funcAmp_0(self, v):
        """
        Compute the term in the integral. Integrate from 0 to 1.
        
        sigmat: Width of Gaussian kernel
        """
        gaussian = np.exp(-(v * self.vsini)**2/(2*self.sigmat**2)) / np.sqrt(2*np.pi) / self.sigmat
        mu = np.sqrt(1 - v*v)
        u1, u2 = self.u
        denom = np.pi * (1.0 - u1/3.0 - u2/6.0)
        u0p = (1 - u1 - u2) / denom
        u1p = (u1 + u2 + u2) / denom
        u2p = -u2 / denom
        rotkernel = u0p * b0 * mu + u1p * b1 * (mu*mu) + u2p * b2 * (mu*mu*mu)
        return gaussian * rotkernel
    
    def true_anomaly(self,times):
        """
        Calculate the true anomaly
        """
        f = true_anomaly(times,self.T0,self.P,self.aRs,self.i,self.e,self.w)
        return f

    def calc_transit(self,times):
        """
        Calculate transit model of planet
        """
        params = batman.TransitParams()
        params.t0 = self.T0
        params.per = self.P
        params.inc = self.i
        params.rp = self.RpRs
        params.a = self.aRs
        params.ecc = self.e
        params.w = self.w
        params.u = self.u
        params.limb_dark = self.limb_dark
        params.fp = 0.001
        transitmodel = batman.TransitModel(params, times, transittype='primary',exp_time=self.exp_time,
                                         supersample_factor=self.supersample_factor)
        return transitmodel.light_curve(params)

    def planet_XYZ_position(self,times):
        """
        Get the planet XYZ position at times
        """
        X, Y, Z = planet_XYZ_position(times,self.T0,self.P,self.aRs,self.i,self.e,self.w)
        return X, Y, Z

    def Xp(self,times):
        lam, w, i = np.deg2rad(self.lam), np.deg2rad(self.w), np.deg2rad(self.i)
        f = self.true_anomaly(times)
        r = self.aRs*(1.-self.e**2.)/(1.+self.e*np.cos(f)) # distance
        x = -r*np.cos(f+w)*np.cos(lam) + r*np.sin(lam)*np.sin(f+w)*np.cos(i)
        return x

    def evaluate(self,times,base_error=0.):
        sigma = self.sigma
        beta = self.beta
        X = self.Xp(times)
        F = 1.-self.calc_transit(times)
        # vp = X*self._Omega*np.sin(np.deg2rad(self.iS))*self.rstar*aconst.R_sun.value/1000.
        vp = X * self.vsini
        v = -1000./self.a0 * F * vp * ((2*sigma*sigma) / (sigma*sigma + beta*beta))**(3/2) * np.exp(-(vp*vp)/(2*(sigma*sigma+beta*beta)))
        # For diagnostics
        self.vp = vp
        self.X = X
        self.F = F
        if base_error >0:
            return v + np.random.normal(loc=0.,scale=base_error,size=len(v))
        else:
            return v
        
        
class RMBoueMacroturb(RMBoue):
    """
    Evaluate Rossiter McLaughlin effect using the model of Boue+13
    Accounts for macroturbulent broadening
    """
    def XpYp(self,times):
        lam, w, i = np.deg2rad(self.lam), np.deg2rad(self.w), np.deg2rad(self.i)
        f = self.true_anomaly(times)
        r = self.aRs*(1.-self.e**2.)/(1.+self.e*np.cos(f)) # distance
        x = -r*np.cos(f+w)*np.cos(lam) + r*np.sin(lam)*np.sin(f+w)*np.cos(i)
        y = -r*np.cos(f+w)*np.sin(lam) - r*np.cos(lam)*np.sin(f+w)*np.cos(i)
        return x, y
    
    def _theta(self, r, d):
        """
        Theta function from Sacket et al. 1998 (EQ 10)
        
        r: Radius from center of star
        d: Distance between centers of star and planet
        """
        return (d**2.+r**2.-self.RpRs**2.)/(2.*r*d)

    def _limb_dark_quadratic(self, r):
        """
        Quadratic limb darkening
        
        r: Radial coordinate from center of star
        """
        mu = np.sqrt(1 - r*r)
        u1, u2 = self.u
        return 1 - u1 * (1 - mu) - u2 * (1 - mu)**2
    
    def _denom_integrand(self, r, d):
        if r > 1.:
            return 0.
        if d==0:
            return (r*2*np.pi*self._limb_dark_quadratic(r))
        t = self._theta(r, d)
        if np.abs(t) > 1:
            return (r*2*np.pi*self._limb_dark_quadratic(r))
        else:
            return (r*2*np.arccos(t)*self._limb_dark_quadratic(r))
        
    def _num_radial_integrand(self, r, d):
        if r > 1.:
            return 0.
        mu2 = 1 - r*r
        if d==0:
            return (mu2*r*2*np.pi*self._limb_dark_quadratic(r))
        t = self._theta(r, d)
        if np.abs(t) > 1:
            return (mu2*r*2*np.pi*self._limb_dark_quadratic(r))
        else:
            return (mu2*r*2*np.arccos(t)*self._limb_dark_quadratic(r))
        
    def _num_tangential_integrand(self, r, d):
        if r > 1.:
            return 0.
        r2 = r*r
        if d==0:
            return (r2*r*2*np.pi*self._limb_dark_quadratic(r))
        t = self._theta(r, d)
        if np.abs(t) > 1:
            return (r2*r*2*np.pi*self._limb_dark_quadratic(r))
        else:
            return (r2*r*2*np.arccos(t)*self._limb_dark_quadratic(r))
    
    def evaluate(self,times,base_error=0.):
        sigma = self.sigma
        beta = self.beta
        zeta = self.zeta
        X, Y = self.XpYp(times)
        # Compute macroturbulent broadening widths
        # ds = np.sqrt(X**2 + Y**2)
        # low_lim = np.maximum(0, ds - self.RpRs)
        # upp_lim = np.minimum(1, ds + self.RpRs)
        # denoms = np.array([quad(self._denom_integrand, low_lim[i], upp_lim[i], args=(ds[i]))[0] for i in range(len(ds))])
        # num_radial = np.array([quad(self._num_radial_integrand, low_lim[i], upp_lim[i], args=(ds[i]))[0] for i in range(len(ds))])
        # num_tangential = np.array([quad(self._num_tangential_integrand, low_lim[i], upp_lim[i], args=(ds[i]))[0] for i in range(len(ds))])
        # epsilon = 1e-10
        # betaR2 = beta*beta + zeta*zeta * num_radial / (denoms + epsilon)
        # betaT2 = beta*beta + zeta*zeta * num_tangential / (denoms + epsilon)
        betaR2 = beta*beta + zeta*zeta/2
        betaT2 = beta*beta + zeta*zeta/2
        F = 1.-self.calc_transit(times)
        vp = X * self.vsini
        v = -1000./2/self.a0 * F * vp *(
            ((2*sigma*sigma) / (sigma*sigma + betaR2))**(3/2) * np.exp(-(vp*vp)/(2*(sigma*sigma+betaR2))) +
            ((2*sigma*sigma) / (sigma*sigma + betaT2))**(3/2) * np.exp(-(vp*vp)/(2*(sigma*sigma+betaT2))))
        # For diagnostics
        self.vp = vp
        self.X = X
        self.F = F
        if base_error >0:
            return v + np.random.normal(loc=0.,scale=base_error,size=len(v))
        else:
            return v


def fibonacci_disk_sampling(N):
    """
    Generate N points in a Fibonacci spiral inside the unit disk.

    Returns arrays x, y.
    """
    phi = (1.0 + np.sqrt(5.0)) / 2.0  # golden ratio
    alpha = 2.0 * np.pi / (phi**2)

    k = np.arange(N)  # 0..N-1
    r = np.sqrt((k + 0.5)/N)  # radius
    theta = k * alpha

    x = r * np.cos(theta)
    y = r * np.sin(theta)
    return x, y


class RMReloaded(object):
    NUM_POINTS = 10000
    GRID_AREA = np.pi / NUM_POINTS
    grid_x, grid_y = fibonacci_disk_sampling(NUM_POINTS)
    
    def __init__(self, times, P, T0, aRs, i, RpRs, e, w, u):
        """
        Evaluate Rossiter McLaughlin Reloaded effect using Cegla et al. 2016

        INPUT:
            times - Fixed set of times at which to evaluate the RM effect
            -- Planet properties only required for computing true anomaly
            P - Period in days
            T0 - Transit center
            aRs - a/R*
            i - planet orbital inclination in degrees
            RpRs - radius ratio
            e - eccentricity
            w - omega in degrees
            u - [u1,u2] where u1 and u2 are the quadratic limb-dark coefficients
            -- RM parameters
            lam - sky-projected obliquity in deg
            vsini - sky-projected rotational velocity in km/s

        EXAMPLE:
            times = np.linspace(-0.05,0.05,200)
            T0 = 0.
            P = 3.48456408
            aRs = 21.09
            i = 89.
            vsini = 8.7
            rprs = np.sqrt(0.01)
            e = 0.
            w = 90.
            lam = 45.
            u = [0.3,0.3]
            R = RMHirano(lam,vsini,P,T0,aRs,i,rprs,e,w,u,limb_dark='quadratic')
            rm = R.evaluate(times)

            fig, ax = plt.subplots()
            ax.plot(times,rm)
        """
        self.times = times
        # Planet orbital parameters
        self.P = P
        self.T0 = T0
        self.aRs = aRs
        self.i = i
        self.RpRs = RpRs
        self.e = e
        self.w = w
        self.u = u
        # Location of the center of the planet at a given time
        self.Xp, self.Yp = self.XpYp(times)
        # Grid translated and scaled to the planet's position at each time.
        self.Xp_grid = self.Xp[:, np.newaxis] + self.grid_x * self.RpRs
        self.Yp_grid = self.Yp[:, np.newaxis] + self.grid_y * self.RpRs
        # Radial distance of each point
        self.r_grid = np.sqrt(self.Xp_grid**2 + self.Yp_grid**2)
        self.mask_grid = self.r_grid < 1
        # Limb-darkened flux at each point
        self.F = self._limb_dark_quadratic(self.r_grid)
        self.F[~self.mask_grid] = 0
        # Flux normalization
        self.flux_norm = np.sum(self.F * self.mask_grid, axis=1)

    def _limb_dark_quadratic(self, r):
        """
        Quadratic limb darkening
        
        r: Radial coordinate from center of star
        """
        mu = np.sqrt(1 - r*r)
        u1, u2 = self.u
        return 1 - u1 * (1 - mu) - u2 * (1 - mu)**2

    def true_anomaly(self,times):
        """
        Calculate the true anomaly
        """
        f = true_anomaly(times,self.T0,self.P,self.aRs,self.i,self.e,self.w)
        return f

    def XpYp(self,times):
        """
        Unlike the function used in RMHirano, the coordinate system used here has
        the y-axis aligned with the planet's orbital axis.
        """
        w, i = np.deg2rad(self.w), np.deg2rad(self.i)
        f = self.true_anomaly(times)
        r = self.aRs*(1.-self.e**2.)/(1.+self.e*np.cos(f)) # distance
        x = -r*np.cos(f+w)
        y = -r*np.sin(f+w)*np.cos(i)
        return x, y

    def evaluate(self,lam, vsini, istar=90.0, alpha=None, times=None):
        if times is None:
            Xp, Yp = self.Xp_grid, self.Yp_grid
            mask_grid = self.mask_grid
            F = self.F
            flux_norm = self.flux_norm
        else:
            Xp, Yp = self.XpYp(times)
            Xp = Xp[:, np.newaxis] + self.grid_x * self.RpRs
            Yp = Yp[:, np.newaxis] + self.grid_y * self.RpRs
            r_grid = np.sqrt(Xp**2 + Yp**2)
            mask_grid = r_grid < 1
            F = self._limb_dark_quadratic(r_grid)
            F[~mask_grid] = 0
            flux_norm = np.sum(F * mask_grid, axis=1)

        # Rotate coordinates by projected obliquity
        Xorth = Xp * np.cos(np.deg2rad(lam)) - Yp * np.sin(np.deg2rad(lam))
        Yorth = Xp * np.sin(np.deg2rad(lam)) + Yp * np.cos(np.deg2rad(lam))
        # Compute stellar velocity for each point
        vstel = Xorth * vsini
        if alpha is not None:
            # Account for differential rotation
            Zorth = np.sqrt(1 - Xorth**2 - Yorth**2)
            beta = np.pi/2 - np.deg2rad(istar)
            sin_lat = Zorth * np.sin(beta) + Yorth * np.cos(beta)
            vstel *= (1 - alpha * sin_lat * sin_lat)
        # Brightness averaged stellar velocity
        v = np.sum(F * vstel * mask_grid, axis=1) / flux_norm
        
        return v
    

def true_anomaly(time,T0,P,aRs,inc,ecc,omega):
    """
    Uses the batman function to get the true anomaly. Note that some 

    INPUT:
        time - in days
        T0 - in days
        P - in days
        aRs - in a/R*
        inc - in deg
        ecc - eccentricity
        omega - omega in deg

    OUTPUT:
        True anomaly in radians
    """
    # Some of the values here are just dummy values (limb dark etc.) to allow us to get the true anomaly
    params = batman.TransitParams()
    params.t0 = T0                           #time of inferior conjunction
    params.per = P                           #orbital period
    params.rp = 0.1                          #planet radius (in units of stellar radii)
    params.a = aRs                           #semi-major axis (in units of stellar radii)
    params.inc = inc                         #orbital inclination (in degrees)
    params.ecc = ecc                         #eccentricity
    params.w = omega                         #longitude of periastron (in degrees)
    params.u = [0.3,0.3]                     #limb darkening coefficients [u1, u2]
    params.limb_dark = "quadratic"           #limb darkening model
    m = batman.TransitModel(params, time)    #initializes model
    return m.get_true_anomaly()

def planet_XYZ_position(time,T0,P,aRs,inc,ecc,omega):
    """
    Get planet XYZ position

    INPUT:
        time - in days
        T0 - in days
        P - in days
        aRs - in a/R*
        inc - in deg
        ecc - eccentricity
        omega - omega in deg

    OUTPUT:
        X - planet X position
        Y - planet Y position
        Z - planet Z position

    EXAMPLE:
        Rstar = 1.
        Mstar = 1.
        inc = 90.
        ecc = 0.9
        omega = -90.
        P = 1.1
        T0 = 1.1
        Rp = 0.1
        aRs =
        print(aRs)
        x_1, y_1, z_1 = planet_XYZ_position(time,T0,P,aRs,inc,ecc,omega)
        fig, ax = plt.subplots()
        ax.plot(time,x_1)
    """
    f = true_anomaly(time,T0,P,aRs,inc,ecc,omega) # true anomaly in radiance
    omega = np.deg2rad(omega)
    inc = np.deg2rad(inc)
    r = aRs*(1.-ecc**2.)/(1.+ecc*np.cos(f)) # distance
    X = -r*np.cos(omega+f)
    Y = -r*np.sin(omega+f)*np.cos(inc)
    Z = r*np.sin(omega+f)*np.sin(inc)
    return X, Y, Z

def get_rv_curve(times_jd,P,tc,e,omega,K):
    """
    A function to calculate an RV curve as a function of time

    INPUT:
        times_jd - times in bjd
        P - period in days
        tc - transit center
        e - eccentricity
        omega - omega in degrees
        K - semi-amplitude in m/s

    OUTPUT:
        RV curve in m/s
    """
    t_peri = radvel.orbit.timetrans_to_timeperi(tc=tc,per=P,ecc=e,omega=np.deg2rad(omega))
    rvs = radvel.kepler.rv_drive(times_jd,[P,t_peri,e,np.deg2rad(omega),K])
    return rvs

def u1_u2_from_q1_q2(q1,q2):
    u1, u2 = 2.*np.sqrt(q1)*q2, np.sqrt(q1)*(1.-2*q2)
    return u1, u2

def b_from_aRs_and_i(aRs,i):
    return aRs*np.cos(np.deg2rad(i))

def aRs_from_Tdur_tau(Tdur, tau, rprs, P, e=0.0, omega=0.0):
    """
    Compute a/Rstar from transit observables.
    
    Equation (27) from Winn 2010
    Applies in the limit Rp << Rstar << a and non-grazing transits
    
    $$
    Rstar/a = (pi / delta^(1/4)) * (sqrt(Ttot^2 - Tfull^2) / P) * ((1 + e sin(omega)) / sqrt(1 - e^2))
    $$
    """
    Tfull  =Tdur - 2*tau
    aRs    =((2*np.sqrt(rprs)) / np.pi) * (P / np.sqrt(Tdur*Tdur - Tfull*Tfull)) * (np.sqrt(1-e*e) / (1 + e * np.sin(omega)))
    return aRs

def b_from_Tdur_tau(Tdur, tau, rprs):
    """
    Compute impact parameter from transit observables.
    
    Equation (26) from Winn 2010
    Applies in the limit Rp << Rstar << a and non-grazing transits
    
    $$
    b^2 = ((1 - sqrt(delta))^2 - (Tfull / Tdur)^2 * (1 + sqrt(delta))^2) / (1 - (Tfull / Tdur)^2)
    $$
    """
    Tfull = Tdur - 2*tau
    Tfull_Tdur2 = (Tfull / Tdur)**2
    b2 = ((1 - rprs)**2 - Tfull_Tdur2 * (1 + rprs)**2) / (1 - Tfull_Tdur2)
    return np.sqrt(b2)

    
def aRs_from_Tdur_Tfull(Tdur, Tfull, rprs, P, e=0.0, omega=0.0):
    """
    Compute a/Rstar from transit observables.
    
    Equation (27) from Winn 2010
    Applies in the limit Rp << Rstar << a and non-grazing transits
    
    $$
    Rstar/a = (pi / delta^(1/4)) * (sqrt(Ttot^2 - Tfull^2) / P) * ((1 + e sin(omega)) / sqrt(1 - e^2))
    $$
    """
    aRs    =((2*np.sqrt(rprs)) / np.pi) * (P / np.sqrt(Tdur*Tdur - Tfull*Tfull)) * (np.sqrt(1-e*e) / (1 + e * np.sin(omega)))
    return aRs

def b_from_Tdur_Tfull(Tdur, Tfull, rprs):
    """
    Compute impact parameter from transit observables.
    
    Equation (26) from Winn 2010
    Applies in the limit Rp << Rstar << a and non-grazing transits
    
    $$
    b^2 = ((1 - sqrt(delta))^2 - (Tfull / Tdur)^2 * (1 + sqrt(delta))^2) / (1 - (Tfull / Tdur)^2)
    $$
    """
    Tfull_Tdur2 = (Tfull / Tdur)**2
    b2 = ((1 - rprs)**2 - Tfull_Tdur2 * (1 + rprs)**2) / (1 - Tfull_Tdur2)
    return np.sqrt(b2)
    

def simulate_rm_curve(P,aRs,inc,vsini,rprs,rvprec,exptime,e,omega,vmacro,lam=0.,T0=0.,u=[0.4,0.2],ntransits=1,NBIN=2,seed=1234,sim_dur=6.,R=110000,
                      ax=None,targetname='',instrumentname='',savefig=True):
    """
    Simulate RM curve for a given target

    INPUT:
        P - period in days
        aRs - a/R*
        inc - inclination in deg
        vsini - vsini in km/s
        rprs - Rp/R*
        rvprec - rvprecision in a given timebin given by *exptime*
        exptime - exposure time in s
        e - eccentricity
        omega - argument of periastron in deg
        lam - lambda in deg
        T0 - transit midpoint (defaults to 0)
        u - quadratic limb-darkening params
        ntransits - how many transits observed
        NBIN - how often to bin the overplotted binned curve (just used for plotting)
        seed - random seed
        sim_dur - how many hours to simulate the data
        R - resolution of the spectrograph
        ax - axis instance
        targetname - target name
        instrumentname - instrument name

    OUTPUT:
       time - simulated time in hours
       rv - simulated RM curve
       errors - errors in m/s
    
    EXAMPLE:
        rvprec = astropylib.maroonx_help.get_maroonx_rvprec_snr_cadence(13.8941,4400.,exptime=500.,vsini=2.2,)
        x, y, yerr = astropylib.exoplanet_functions.simulate_rm_curve(instrument='Maroon-X',
                                                     target='K2-295b',
                                                     P=4.024867,
                                                     aRs=13.854,
                                                     inc=89.3,
                                                     vsini=2.2,
                                                     rprs=0.1304,
                                                     rvprec=3.4475,
                                                     exptime=600.,
                                                     sim_dur=6.)
    """
    np.random.seed(seed)

    zbeta = 300000./R
    beta = np.sqrt(zbeta**2. + vmacro**2.)
    sigma = vsini/1.31
    impact_parameter = b_from_aRs_and_i(aRs,inc)

    # ERROR AND OBSTIME
    error = rvprec/np.sqrt(ntransits)
    exptime = exptime/86400. # change from s to days
    x = np.linspace(-sim_dur/(2*24),sim_dur/(2*24),num=200)
    _f = get_lc_batman(x,T0,P,inc,rprs,aRs,e,omega,u=u)
    _m = _f < 1.
    tdur = x[np.where(_m)[0][-1]]-x[np.where(_m)[0][0]]
    num_in_transit = int(tdur/exptime)
    print('Transit duration:',tdur*24,'hours')
    print('Number of Points in Transit:',num_in_transit)

    # Model
    RH = RMHirano(lam=lam,vsini=vsini,P=P,T0=T0,aRs=aRs,i=inc,RpRs=rprs,e=e,w=omega,u=u,
                        beta=beta,sigma=sigma,supersample_factor=7,exp_time=exptime,limb_dark='quadratic')
    rm_hirano = RH.evaluate(x)
    print('Amplitude: {}m/s'.format(np.max(rm_hirano)))

    # Observed
    x_obs = np.arange(-sim_dur/(2*24),sim_dur/(2*24),exptime)
    errors = np.ones(len(x_obs))*error
    rm_obs_hirano = RH.evaluate(x_obs,base_error=error)
    rm_obs_hirano_noerror = RH.evaluate(x_obs,base_error=0.)
    res = rm_obs_hirano - rm_obs_hirano_noerror

    ###############################
    # Figure
    if ax is None:
        fig, ax = plt.subplots(dpi=200)
    ax.plot(x*24.,rm_hirano,color='crimson')
    ax.errorbar(x_obs*24.,rm_obs_hirano,yerr=error,color="black",marker='o',lw=0,elinewidth=1,
                capsize=4,mew=0.5,
                label='{:.0f}s exposures, {} transits (rvprec={:0.1f}m/s)'.format(exptime*86400.,ntransits,error),
                alpha=0.2)

    # Binning w error
    df_bin_err = utils.bin_data_with_errors(x_obs,rm_obs_hirano,errors,NBIN)
    ax.errorbar(df_bin_err.x*24.,df_bin_err.y,df_bin_err.yerr,color=utils.CP[0],marker='o',lw=0,markersize=8,
                label='Bin {}x'.format(NBIN),elinewidth=1,capsize=4,mew=1)

    ax.legend(loc="upper right",fontsize=8)
    utils.ax_apply_settings(ax)
    ax.set_xlabel('Time [hours]',fontsize=12)
    ax.set_ylabel('RV [m/s]',fontsize=12)
    #ax.set_ylim(-25,35)
    
    #########################
    # SNR
    snr = utils.rm_SNR(0,impact_parameter,num_in_transit,np.max(rm_hirano),error)
    print("SNR: {}".format(snr))
    err_lam = utils.rm_sigma_lambda(0.,impact_parameter,num_in_transit,np.max(rm_hirano),error)
    print("lambda error: {}".format(err_lam))
    ax.set_title('{} b RM effect\nassuming vsini = {}km/s\nExpected SNR={:0.2f}'.format(targetname,vsini,snr),fontsize=12)

    savename = '{}_vsini_{}_ntransits_{}.png'.format(targetname,vsini,ntransits)
    print('###########')
    print(savename)
    print('###########')
    SN = np.sqrt(stats_help.chi2(rm_obs_hirano,error*np.ones(len(rm_obs_hirano)),2)-stats_help.chi2(res,error*np.ones(len(rm_obs_hirano)),2))
    TITLE = '{} {} RM effect\nAssuming vsini = {}km/s\nSimulated SNR={:0.2f}, Expected SNR={:0.2f}'.format(targetname,instrumentname,vsini,SN,snr)
    TITLE += '\nExpected $\Delta \lambda = {:0.2f}$deg'.format(err_lam)
    ax.set_title(TITLE,fontsize=12)
    print(SN,snr)
    fig.tight_layout()
    if savefig:
        fig.savefig(savename,dpi=200)
    return x_obs, rm_obs_hirano, errors


def get_lc_batman(times,t0,P,i,rprs,aRs,e,omega,u,supersample_factor=1,exp_time=0.,limbdark="quadratic"):
    """
    Calls BATMAN and returns the transit model

    INPUT:
        times - times to evaluate lc
        t0 - transit midpoint
        P - period in days
        i - inclination 
        rprs - Rp/R*
        aRs - a/R*
        e - eccentricity 
        omega - argument of periastron
        u - limb darkening [u1,u2]
        supersample_factor=1
        exp_time=0. - exposure time
        limbdark="quadratic"

    OUTPUT:
        lc - the lightcurve model at *times*
    """
    supersample_factor = int(supersample_factor)
    params = batman.TransitParams()
    params.t0 = t0
    params.per = P
    params.inc = i
    params.rp = rprs
    params.a = aRs
    params.ecc = e
    params.w = omega
    params.u = u
    params.limb_dark = limbdark
    params.fp = 0.001     
    transitmodel = batman.TransitModel(params, times, transittype='primary',
                                       supersample_factor=supersample_factor,
                                       exp_time=exp_time)
    lc = transitmodel.light_curve(params)
    return lc 


