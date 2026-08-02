# Application resources

`codebook.xml` maps dataset columns to descriptions and workbench groups.
`settings.xml` retains the legacy plotting palette configuration.

Both files are loaded through `src.mn_sentencing_explorer.paths`; callers must not
depend on the process working directory.
