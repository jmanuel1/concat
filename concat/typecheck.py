import concat.astutils
import concat.level1.preamble_types
import concat.level1.typecheck
import concat.level2.preamble_types
import concat.level2.typecheck

def check(environment: concat.level1.typecheck.Environment, program: concat.astutils.WordsOrStatements, source_dir: str = '.') -> None:
    environment = concat.level1.typecheck.Environment(
        {**concat.level1.preamble_types.types, **concat.level2.preamble_types.types, **concat.level2.typecheck.builtin_environment, **environment})
    concat.level1.typecheck.infer(
        environment,
        program,
        (concat.level2.typecheck.infer,),
        True,
        source_dir
    )
