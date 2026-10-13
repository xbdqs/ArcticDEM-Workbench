"""Method identities and evidence limits shared by GUI, jobs and reports."""

REGISTERED_METHODS = ('vertical', 'translation', 'nuth_kaab', 'joint_gradient')
FROZEN_JOINT_SHA256 = '0ca918973285db1772da9d17a143238652edbf48af61e5e31f57a7b8e1064f9e'

METHOD_LABELS = {
    'none': 'Raw DoD — no registration',
    'vertical': 'Stable-terrain vertical shift',
    'translation': 'Direct robust 3D translation',
    'nuth_kaab': 'Legacy internal Nuth–Kääb variant',
    'joint_gradient': 'Joint-gradient 3D translation (RUN24 controlled validation)',
    'compare': 'Compare four registered methods (same masks/AOI)',
}

METHOD_NOTES = {
    'none': 'Raw DoD applies no registration. Inspect grid, quality coverage and vertical references before interpreting differences.',
    'vertical': 'Vertical-only correction requires independently defensible stable terrain. It does not estimate horizontal offsets.',
    'translation': 'Direct robust XYZ fits height residuals. RUN24 contained accepted fits with incorrect known-shift recovery, especially on weak terrain. Convergence and low residuals do not establish accuracy.',
    'nuth_kaab': 'Legacy internal slope/aspect implementation, retained for reproducibility. RUN24 recorded rejected and accepted-but-inaccurate fits. This is not the demcoreg or xDEM implementation.',
    'joint_gradient': 'Frozen RUN24 joint horizontal/vertical estimator with guarded support and at most 12,000 fit cells. Controlled recovery passed; real-data accuracy remains to be evaluated. Use reliable stable terrain and inspect held-out residuals.',
    'compare': 'Runs vertical, direct XYZ, legacy internal Nuth–Kääb and joint-gradient methods. Initial display follows a fixed method order, not residual ranking. Export a case report for comparison on common valid support.',
}


def method_metadata(method):
    data = {'id': method, 'label': METHOD_LABELS[method], 'limitations': METHOD_NOTES[method],
            'automatic_scientific_selection': False,
            'external_accuracy_established_by_controlled_tests': False}
    if method == 'joint_gradient':
        data.update(frozen_engine_sha256=FROZEN_JOINT_SHA256,
                    implementation='frozen RUN24 engine with a production input/support adapter',
                    fit_sample_limit=12000, controlled_evidence='RUN24: 36/36 parameter checks; 8/8 injected-change checks')
    return data
