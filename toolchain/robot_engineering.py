"""Deterministic engineering calculations; never writes to a motor or controller."""
import math


def number(value, name, low=-1e12, high=1e12):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError(name+' must be finite in ['+str(low)+', '+str(high)+']')
    return float(value)


def fields(args, required, optional=()):
    if not isinstance(args,dict) or set(args)-set(required)-set(optional):
        raise ValueError('Unknown calculation fields; check the tool schema')
    missing=set(required)-set(args)
    if missing: raise ValueError('Missing required parameters: '+', '.join(sorted(missing)))


def current_to_torque(args):
    fields(args,('current_A','kt_Nm_per_A','current_basis','kt_current_basis'),
           ('current_offset_A','gear_ratio','efficiency'))
    bases=('dc_armature','iq_peak','iq_rms','phase_peak','phase_rms')
    if args['current_basis'] not in bases or args['kt_current_basis'] not in bases:
        raise ValueError('Identify current convention: dc_armature/iq_peak/iq_rms/phase_peak/phase_rms. DC bus current and load percent are not torque current.')
    if args['current_basis']!=args['kt_current_basis']:
        raise ValueError('Current and Kt use different conventions; obtain a matched datasheet definition, do not guess a sqrt(2) or sqrt(3) conversion')
    current=number(args['current_A'],'current_A')
    kt=number(args['kt_Nm_per_A'],'kt_Nm_per_A',1e-12,1e6)
    offset=number(args.get('current_offset_A',0),'current_offset_A')
    motor=kt*(current-offset)
    result={'motor_torque_Nm':motor,'corrected_current_A':current-offset,'current_basis':args['current_basis'],
            'formula':'tau_motor = Kt * (I - signed_sensor_offset)', 'classification':'electromagnetic_torque_estimate',
            'assumptions':['Kt is constant and uses the same current convention; saturation, temperature and friction are not modeled.',
                           'current_offset_A is a signed sensor zero offset, not an unsigned no-load-current subtraction.'],
            'measured_output_torque':False,'hardware_command_sent':False}
    if 'gear_ratio' in args or 'efficiency' in args:
        if not {'gear_ratio','efficiency'}<=set(args): raise ValueError('Both gear_ratio and efficiency are required for output-shaft torque')
        ratio=number(args['gear_ratio'],'gear_ratio = motor_speed / output_speed',1e-9,1e9)
        efficiency=number(args['efficiency'],'efficiency',1e-9,1)
        result.update(output_torque_Nm=motor*ratio*efficiency,output_formula='tau_output = tau_motor * reduction_ratio * efficiency',
                      transmission_model='Motor drives load through reduction; this is not a reverse/backdriving efficiency model.')
    return result


def pid_trial(args):
    fields(args,('kp','ki','kd','inertia_kg_m2','damping_Nm_s_per_rad','torque_limit_Nm','target_rad'),
           ('dt_s','duration_s','initial_rad','derivative_filter_s','load_torque_Nm'))
    kp,ki,kd=(number(args[k],k,0,1e6) for k in ('kp','ki','kd'))
    inertia=number(args['inertia_kg_m2'],'inertia_kg_m2',1e-9,1e6)
    damping=number(args['damping_Nm_s_per_rad'],'damping_Nm_s_per_rad',0,1e6)
    limit=number(args['torque_limit_Nm'],'torque_limit_Nm',1e-9,1e6)
    target=number(args['target_rad'],'target_rad',-1e4,1e4)
    dt=number(args.get('dt_s',.001),'dt_s',1e-5,.1)
    duration=number(args.get('duration_s',3),'duration_s',dt,60)
    steps=int(duration/dt)
    if steps>20000: raise ValueError('At most 20000 PID steps; increase dt or shorten duration')
    q=number(args.get('initial_rad',0),'initial_rad',-1e4,1e4);initial=q
    load=number(args.get('load_torque_Nm',0),'load_torque_Nm')
    filt=number(args.get('derivative_filter_s',.01),'derivative_filter_s',0,10)
    velocity=integral=derivative=0.;rows=[];saturated=0;iae=0.
    for step in range(steps):
        error=target-q
        # Derivative on measurement avoids target-step kick; low-pass filter rejects noise.
        derivative += dt/(filt+dt)*(velocity-derivative)
        trial_i=integral+ki*error*dt
        raw=kp*error+trial_i-kd*derivative
        if not ((raw>limit and error>0) or (raw<-limit and error<0)):
            integral=trial_i
        raw=kp*error+integral-kd*derivative
        torque=max(-limit,min(limit,raw));saturated+=abs(raw)>limit
        # Exact constant-torque damped-rotor propagation over a sample.
        net=torque-load
        if damping>0:
            decay=math.exp(-damping*dt/inertia);v_inf=net/damping
            q+=v_inf*dt+(velocity-v_inf)*(-math.expm1(-damping*dt/inertia))*inertia/damping
            velocity=v_inf+(velocity-v_inf)*decay
        else:
            acceleration=net/inertia;q+=velocity*dt+.5*acceleration*dt*dt;velocity+=acceleration*dt
        if not all(math.isfinite(x) and abs(x)<1e9 for x in (q,velocity,integral)):
            raise ValueError('Trial diverged; gains/time step/plant parameters need review')
        iae+=abs(error)*dt
        rows.append({'time_s':(step+1)*dt,'position_rad':q,'velocity_rad_s':velocity,'torque_Nm':torque,'integral_torque_Nm':integral})
    displacement=target-initial
    overshoot=max([0.]+[(r['position_rad']-target)*(1 if displacement>=0 else -1) for r in rows])
    return {'execution':'offline_single_axis_trial','plant':'J*qdd + b*qd = torque - constant_load',
            'controller':'PID; derivative on filtered measurement; conditional-integration anti-windup',
            'gain_units':{'kp':'Nm/rad','ki':'Nm/(rad*s)','kd':'Nm*s/rad'},
            'final_error_rad':target-q,'overshoot_rad':overshoot,'integrated_absolute_error_rad_s':iae,
            'saturation_fraction':saturated/steps,'samples':rows,'hardware_command_sent':False,
            'limitations':'Ideal torque source; no current-loop delay, encoder quantization, Coulomb friction or flexible transmission. Not automatically deployable gains.'}
