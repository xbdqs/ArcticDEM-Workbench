import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_geom
from pyproj import Transformer,Geod
from arcticdem_workbench.common import write_json,sha256
from arcticdem_workbench.raster import Grid,write_raster
from arcticdem_workbench.reporting import export_report
from arcticdem_workbench.support import compute_support


class SupportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.grid=Grid(from_origin(500000,-1200000,4,4),rasterio.crs.CRS.from_epsg(3413),12,12)
        self.epochs=[{'id':'e'+str(i),'date':f'{2010+2*i}-08-01T00:00:00Z','dem_sha256':'same-dem-'+str(i),
                      'units':'m','vertical_datum':'common','image_ids':['image-'+str(i)]} for i in range(3)]

    def tearDown(self):self.tmp.cleanup()

    def create(self,method,stack=None,grid=None,domain=None,hold=None,fit=None):
        grid=grid or self.grid;path=self.root/method;path.mkdir()
        arr=np.stack([np.full(grid.shape,v,dtype='float32') for v in (100,103,107)]) if stack is None else stack
        profile=grid.profile();profile['count']=3
        with rasterio.open(path/'epoch_stack.tif','w',**profile) as dst:
            for k,e in enumerate(self.epochs):
                dst.write(np.where(np.isfinite(arr[k]),arr[k],-9999).astype('float32'),k+1)
                dst.set_band_description(k+1,e['date']);dst.update_tags(k+1,source_id=e['id'])
        domain=np.ones(grid.shape,dtype=bool) if domain is None else domain
        hold=np.ones(grid.shape,dtype=bool) if hold is None else hold
        fit=np.zeros(grid.shape,dtype=bool) if fit is None else fit
        for name,data in [('registered_common_valid_mask',np.where(domain,np.all(np.isfinite(arr),axis=0),255)),('fit_mask',fit),('validation_mask',hold)]:
            write_raster(path/(name+'.tif'),data,grid,dtype='uint8',nodata=255)
        write_json(path/'report.json',{'method':method,'status':'completed','epochs':self.epochs,'pair_statistics':[],
                   'validation_kind':'controlled test holdout','warnings':[]})
        write_json(path/'job.json',{'block_pixels':8,'resolution':4,'network':'all','require_match':True})
        return method,path,'completed',''

    def polygon(self,fid='target',outer=None,holes=None):
        outer=outer or [[2,2],[10,2],[10,10],[2,10],[2,2]]
        rings=[outer]+(holes or [])
        geom={'type':'Polygon','coordinates':[[list(self.grid.transform*(x,y)) for x,y in ring] for ring in rings]}
        return {'type':'Feature','id':fid,'properties':{'role':'target','name':fid},'geometry':transform_geom(self.grid.crs,4326,geom)}

    def test_all_epochs_all_methods_remove_coverage_bias(self):
        a=np.stack([np.full(self.grid.shape,v,dtype='float32') for v in (100,103,107)])
        b=a.copy();a[2,:4,:4]=200;b[1,:4,:4]=np.nan
        folders=[self.create('vertical',a),self.create('translation',b)]
        before={str(p):sha256(p) for _,f,_,_ in folders for p in f.iterdir()}
        result=compute_support(folders,self.root/'support',log=lambda s:None)
        self.assertEqual(result['common_cells'],128)
        self.assertTrue(all(r['n']==128 for r in result['region_statistics']))
        final=[r for r in result['region_statistics'] if r['i']==0 and r['j']==2]
        self.assertEqual(len(final),2)
        for row in final:self.assertAlmostEqual(row['area_weighted_mean_dh_m'],7,places=8)
        self.assertGreater(float(np.mean(a[2]-a[0])),7)
        with rasterio.open(self.root/'support'/'common_valid_mask.tif') as src:
            mask=src.read(1);self.assertTrue((mask[:4,:4]==0).all());self.assertEqual(int((mask==1).sum()),128)
        self.assertEqual(before,{p:sha256(p) for p in before})

    def test_holes_and_signed_volume_use_ground_area(self):
        a=np.stack([np.full(self.grid.shape,v,dtype='float32') for v in (100,103,107)])
        a[2]=98;folders=[self.create('vertical',a)]
        hole=[[4,4],[4,8],[8,8],[8,4],[4,4]]
        obj={'type':'FeatureCollection','features':[self.polygon(holes=[hole])]}
        out=compute_support(folders,self.root/'support',obj,log=lambda s:None)
        row=next(r for r in out['region_statistics'] if r['region_id']=='target' and r['i']==0 and r['j']==2)
        self.assertEqual(row['n'],48);self.assertEqual(row['positive_volume_m3'],0)
        to_wgs=Transformer.from_crs(3413,4326,always_xy=True);geod=Geod(ellps='WGS84');area=0.
        for r in range(2,10):
            for c in range(2,10):
                if 4<=r<8 and 4<=c<8:continue
                xy=[self.grid.transform*(x,y) for x,y in [(c,r),(c+1,r),(c+1,r+1),(c,r+1)]]
                lon,lat=to_wgs.transform(*zip(*xy));area+=abs(geod.polygon_area_perimeter(lon,lat)[0])
        self.assertAlmostEqual(row['ground_area_m2']/area,1,places=5)
        self.assertAlmostEqual(row['net_volume_m3']/(-2*area),1,places=5)
        self.assertEqual(row['negative_volume_m3'],row['net_volume_m3'])
        self.assertIsNone(row['volume_uncertainty_m3'])

    def test_common_validation_excludes_fit_in_every_method(self):
        hold1=np.zeros(self.grid.shape,dtype=bool);hold1[:8]=True
        hold2=np.zeros_like(hold1);hold2[2:]=True
        fit=np.zeros_like(hold1);fit[3,3:7]=True
        folders=[self.create('vertical',hold=hold1),self.create('translation',hold=hold2,fit=fit)]
        result=compute_support(folders,self.root/'support',log=lambda s:None)
        self.assertEqual(result['validation_cells'],6*12-4)
        self.assertFalse(result['fit_membership_equal']);self.assertFalse(result['validation_membership_equal'])
        for row in result['validation_statistics']:self.assertEqual(row['n'],68)
        with rasterio.open(self.root/'support'/'common_validation_mask.tif') as src:self.assertEqual(src.read(1)[3,4],0)

    def test_empty_and_outside_regions_remain_missing_not_zero(self):
        a=np.full((3,12,12),100,dtype='float32');a[1,:,:6]=np.nan;a[2,:,6:]=np.nan
        folders=[self.create('vertical',a)]
        obj={'type':'FeatureCollection','features':[self.polygon(),self.polygon('outside',[[30,30],[32,30],[32,32],[30,32],[30,30]])]}
        result=compute_support(folders,self.root/'support',obj,log=lambda s:None)
        self.assertEqual(result['common_cells'],0)
        for row in result['region_statistics']:self.assertIsNone(row['net_volume_m3']);self.assertIsNone(row['area_weighted_mean_dh_m'])
        outside=next(r for r in result['regions'] if r['region_id']=='outside')
        self.assertTrue(outside['extends_outside_grid']);self.assertEqual(outside['status'],'outside_analysis_aoi')

    def test_mismatched_grids_and_input_hashes_are_rejected(self):
        a=self.create('vertical');badgrid=Grid(from_origin(500002,-1200000,4,4),self.grid.crs,12,12)
        b=self.create('translation',grid=badgrid)
        with self.assertRaisesRegex(ValueError,'grids differ'):compute_support([a,b],self.root/'bad_grid',log=lambda s:None)
        c=self.create('nuth_kaab');p=c[1]/'report.json';r=json.loads(p.read_text());r['epochs'][0]['dem_sha256']='other';write_json(p,r)
        with self.assertRaisesRegex(ValueError,'input DEM'):compute_support([a,c],self.root/'bad_input',log=lambda s:None)
        self.assertEqual(json.loads((self.root/'bad_grid'/'status.json').read_text())['status'],'failed')

    def test_different_aois_are_not_silently_intersected(self):
        domain=np.ones(self.grid.shape,dtype=bool);domain[0]=False
        a=self.create('vertical');b=self.create('translation',domain=domain)
        with self.assertRaisesRegex(ValueError,'AOI masks differ'):compute_support([a,b],self.root/'support',log=lambda s:None)

    def test_failed_method_listed_and_all_pairs_exported(self):
        a=self.create('vertical');failed=('translation',self.root/'translation','failed','No stable terrain')
        out=compute_support([a,failed],self.root/'support',log=lambda s:None)
        self.assertTrue(out['partial_method_set']);self.assertFalse(out['cross_method'])
        self.assertEqual(out['excluded_methods'][0]['reason'],'No stable terrain');self.assertEqual(out['pair_count'],3)

    def test_report_includes_regions_and_common_point_membership(self):
        a=self.create('vertical');lon,lat=Transformer.from_crs(3413,4326,always_xy=True).transform(*(self.grid.transform*(3.5,3.5)))
        point={'type':'Feature','id':'p1','properties':{'role':'sample','name':'fixed'},'geometry':{'type':'Point','coordinates':[lon,lat]}}
        objects={'type':'FeatureCollection','features':[self.polygon(),point]}
        report=export_report(a[1],self.root/'report',objects,log=lambda s:None)
        self.assertEqual(report['common_support_status'],'completed')
        audit=json.loads((self.root/'report'/'audit.json').read_text());self.assertEqual(audit['common_support']['common_cells'],144)
        html=(self.root/'report'/'report.html').read_text();self.assertIn('Region changes',html)
        import csv
        with (self.root/'report'/'sample_timeseries.csv').open(encoding='utf-8-sig',newline='') as src:
            rows=list(csv.DictReader(src));self.assertTrue(all(row['in_common_support']=='True' for row in rows))

    def test_cancel_does_not_publish_completed_support(self):
        a=self.create('vertical')
        with self.assertRaises(InterruptedError):compute_support([a],self.root/'support',cancel=lambda:True,log=lambda s:None)
        self.assertEqual(json.loads((self.root/'support'/'status.json').read_text())['status'],'cancelled')


if __name__=='__main__':unittest.main()
