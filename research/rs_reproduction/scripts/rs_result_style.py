"""Publication layout for frozen numerical figures 3–6. No calculations are refitted."""
from datetime import datetime
from io import BytesIO
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

COLORS = {'wb':'#183f51','original':'#d9903d','common':'#167f92'}


def save(fig, out, name, dpi):
    for ext in ('png','svg','pdf'):
        target=out/'figures'/(name+'.'+ext)
        if ext=='pdf':
            buffer=BytesIO()
            fig.savefig(buffer,format='pdf',dpi=dpi,bbox_inches='tight',facecolor='white')
            data=buffer.getvalue()
            if not data.rstrip().endswith(b'%%EOF'):raise ValueError('Incomplete PDF export: '+name)
            temporary=target.with_suffix('.pdf.tmp');temporary.write_bytes(data);temporary.replace(target)
        else:
            fig.savefig(target,dpi=dpi,bbox_inches='tight',facecolor='white')
    plt.close(fig)


def controlled(audit,out,dpi,font):
    fig,axs=plt.subplots(1,2,figsize=(8.8,4.4),gridspec_kw={'width_ratios':[1.12,1]})
    rows=[next(r for r in audit['method_aggregate'] if r['method']==key)
          for key in ('translation','nuth_kaab','joint_gradient_candidate')]
    left=np.zeros(3)
    for key,color,label in [('recovery_passed','#147d92','Recovery passed'),
                             ('accepted_but_recovery_failed','#c87b20','Accepted; recovery failed'),
                             ('rejected','#b8c0c7','Fit rejected')]:
        n=np.array([r[key] for r in rows]);axs[0].barh(range(3),n,left=left,color=color,height=.65,label=label)
        for i,v in enumerate(n):
            if v:axs[0].text(left[i]+v/2,i,str(v),ha='center',va='center',weight='bold',
                            color='white' if key=='recovery_passed' else '#20343f')
        left+=n
    axs[0].set_yticks(range(3),['Direct robust\ntranslation','Internal\nNuth–Kääb','Joint\ngradient'])
    axs[0].invert_yaxis();axs[0].set_xlim(0,37);axs[0].set_xticks([0,9,18,27,36])
    axs[0].set_xlabel('Prescribed conditions')
    axs[0].set_title('(a) Parameter recovery',loc='left',fontsize=font+1,weight='bold')
    axs[0].legend(loc='upper left',bbox_to_anchor=(-.04,-.23),frameon=False,fontsize=font-1)
    tiles=['BARRY_NE','BARRY_SE','BATAGAY_NW','BATAGAY_SE']
    for scenario,color,marker,offset,label in [('loss_forward','#b64059','o',-.05,'Injected −5 m'),
                                              ('gain_reverse','#147d92','s',.05,'Injected +3 m')]:
        errors=[100*float(next(r['change_median_error_m'] for r in audit['candidate_change_checks']
                              if r['tile_id']==tile and r['scenario']==scenario)) for tile in tiles]
        axs[1].scatter(errors,np.arange(4)+offset,c=color,marker=marker,s=45,label=label,zorder=3)
    axs[1].set_yticks(range(4),tiles);axs[1].tick_params(axis='y',labelsize=font-1)
    axs[1].invert_yaxis();axs[1].set_xlim(-3.2,1);axs[1].axvline(0,color='#777',ls='--',lw=1)
    axs[1].grid(axis='x',alpha=.2);axs[1].set_xlabel('Median change error (cm)')
    axs[1].set_title('(b) Protected change',loc='left',fontsize=font+1,weight='bold')
    axs[1].legend(loc='upper left',bbox_to_anchor=(-.04,-.23),frameon=False,fontsize=font-1)
    fig.subplots_adjust(left=.17,right=.985,bottom=.35,top=.89,wspace=.72)
    save(fig,out,'RUN24_controlled_results',dpi)


def graphs(graph,out,dpi,font):
    fig,axs=plt.subplots(2,3,figsize=(8.3,6.0))
    coords={0:(0,1),1:(1,1),2:(0,0),3:(1,0)}
    for row,reference in enumerate(('north','west')):
        record=next(r for r in graph['graph_comparability'] if r.get('reference',r.get('fit_reference'))==reference)
        shared={tuple(e) for e in record['common_edges']}
        for col,key in enumerate(('WB_accepted_edges','xDEM_accepted_edges','common_edges')):
            ax=axs[row,col]; ax.axis('off');ax.set_xlim(-.3,1.3);ax.set_ylim(-.47,1.4)
            for edge in record[key]:
                i,j=edge;x=[coords[i][0],coords[j][0]];y=[coords[i][1],coords[j][1]]
                ax.plot(x,y,color='#167f92' if tuple(edge) in shared else '#c5c9cd',lw=3,zorder=1)
            for i,(x,y) in coords.items():
                ax.scatter([x],[y],s=650,color='#183f51',zorder=2)
                ax.text(x,y,str(i),color='white',ha='center',va='center',weight='bold',fontsize=font+1)
            n=len(record[key]);label=f'{n} '+('edge' if n==1 else 'edges')
            if col==2 and reference=='north':label+=' · disconnected'
            ax.text(.5,-.40,label,ha='center',fontsize=font-1)
            ax.set_title(f'({chr(97+row*3+col)}) '+['Workbench','xDEM','Common'][col],loc='left',fontsize=font+1)
        axs[row,0].text(-.45,.5,'North reference' if row==0 else 'West and combined',
                       rotation=90,ha='center',va='center',fontsize=font,weight='bold')
    fig.subplots_adjust(left=.10,right=.99,bottom=.17,top=.94,wspace=.13,hspace=.25)
    fig.text(.12,.07,'0: 2016-08-15   1: 2018-06-08   2: 2024-07-24   3: 2024-09-20',fontsize=font-1)
    fig.text(.12,.025,'Teal: shared edges. Grey: accepted by one implementation only.',fontsize=font-1,color='#56616a')
    save(fig,out,'Batagay_common_graphs',dpi)


def contrasts(graph,out,dpi,font):
    fig,axs=plt.subplots(1,2,figsize=(8.8,4.4),sharey=True)
    pairs=[(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]
    kinds=[('original_software_contrast','#657a91','Original graphs'),
           ('common_graph_software_contrast','#167f92','Common graph'),
           ('graph_selection_contribution','#d9903d','Graph contribution')]
    for i,ref in enumerate(('west','combined')):
        ax=axs[i];x=np.arange(6)
        for j,(kind,color,label) in enumerate(kinds):
            y=[next(r['rmse_m'] for r in graph['paired_contrasts'] if r['region']=='W_SLUMP'
                    and r['reference']==ref and r['contrast']==kind and (r['i'],r['j'])==p) for p in pairs]
            ax.bar(x+(j-1)*.25,y,width=.25,color=color,label=label)
        ax.set_xticks(x,[f'{a}–{b}' for a,b in pairs]);ax.set_xlabel('Acquisition pair')
        ax.set_title(f'({chr(97+i)}) '+ref.capitalize()+' reference',loc='left',fontsize=font+1)
        ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.set_ylim(0,2.85)
    axs[0].set_ylabel('RMS DoD contrast (m)')
    fig.legend(*axs[0].get_legend_handles_labels(),loc='upper center',ncol=3,frameon=False,fontsize=font)
    fig.subplots_adjust(left=.09,right=.99,bottom=.18,top=.79,wspace=.15)
    save(fig,out,'Batagay_graph_contrasts',dpi)


def points(graph,out,dpi,font):
    fig,axs=plt.subplots(4,2,figsize=(7.8,9.3))
    point_names=['P0','P_HEAD','P_N','P_W']
    for row,key in enumerate(point_names):
        for col,ref in enumerate(('west','combined')):
            ax=axs[row,col]
            for variant,color,style,label in [
                (f'{ref}__wb__original',COLORS['wb'],'-','Workbench (both graphs)'),
                (f'{ref}__xdem__original',COLORS['original'],'--','xDEM original'),
                (f'{ref}__xdem__common',COLORS['common'],'-','xDEM common')]:
                rows=sorted([r for r in graph['point_series'] if r['point_key']==key and r['variant']==variant],
                            key=lambda r:r['date'])
                if len(rows)!=4:raise ValueError('Expected four observations for '+variant+' '+key)
                dates=[datetime.fromisoformat(r['date'].replace('Z','+00:00')) for r in rows]
                height=np.array([r['height_m'] for r in rows]);height-=height[0]
                ax.plot(dates,height,style,color=color,marker='o',ms=3.8,lw=1.6,label=label)
            ax.axhline(0,lw=.7,color='#b4bbc0');ax.grid(alpha=.16)
            ax.xaxis.set_major_locator(mdates.YearLocator(4))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
            ax.tick_params(labelsize=font-1)
            ax.set_title(f'({chr(97+row*2+col)}) {ref.capitalize()} · {key}',loc='left',fontsize=font)
            if row<3:ax.tick_params(labelbottom=False)
            else:ax.set_xlabel('Acquisition year')
    fig.legend(*axs[0,0].get_legend_handles_labels(),loc='upper center',ncol=2,frameon=False,fontsize=font-1)
    fig.text(.025,.5,'Height relative to first acquisition (m)',rotation=90,ha='center',va='center',fontsize=font)
    fig.subplots_adjust(left=.11,right=.98,bottom=.08,top=.89,hspace=.35,wspace=.34)
    save(fig,out,'Batagay_fixed_points',dpi)


def render(audit,graph,out,dpi,font):
    plt.rcParams.update({'axes.spines.top':False,'axes.spines.right':False})
    controlled(audit,out,dpi,font)
    graphs(graph,out,dpi,font)
    contrasts(graph,out,dpi,font)
    points(graph,out,dpi,font)
