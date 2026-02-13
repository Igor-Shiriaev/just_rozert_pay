# type: ignore
# TODO: fix types
import asyncio
import time
import typing as ty
from decimal import Decimal

from rozert_pay_shared import rozert_client as external_client
from rozert_pay_shared.rozert_client import TransactionData

client = external_client.RozertClient(
    host="http://localhost:8006",
    merchant_id="1041ff35-3a03-4c64-882f-a7074298ff8e",
    secret_key="DedBN9vBLetZZUKY1Exo6aoWtQdN2M3H",
)

sandbox_client = external_client.RozertClient(
    host="http://localhost:8006",
    merchant_id="c301e973-b755-405c-83f9-b2959ea6a798",
    secret_key="SMCPo6PnAS6LgyZ1zRWvceSC9Q90YB0e",
    sandbox=True,
)


async def wait_event(
    event: ty.Callable[[], ty.Coroutine[ty.Any, ty.Any, bool]], timeout: float = 10
) -> None:
    start = time.time()

    while time.time() - start < timeout:
        if await event():
            return
        await asyncio.sleep(0.1)

    raise TimeoutError("Event did not happen")


async def get_transaction(
    client: external_client.RozertClient, id: str
) -> TransactionData:
    return await client.aget_transaction(id)


async def has_instruction(client: external_client.RozertClient, id: str) -> bool:
    transaction = await get_transaction(client, id)
    return transaction.instruction is not None


async def run_paycash_deposit() -> None:
    result = await client.astart_deposit(
        external_client.DepositRequest(
            wallet_id="84e96bbe-5a4c-4399-b77a-b7e66ef0ed35",
            type="deposit",
            amount=Decimal(10),
            currency="MXN",
        ),
    )

    await wait_event(lambda: has_instruction(client, result.id))
    result = await get_transaction(client, result.id)

    assert result.instruction.type == "instruction_file"


async def run_paycash_sandbox_deposit() -> None:
    result = await sandbox_client.astart_deposit(
        external_client.DepositRequest(
            wallet_id="33d536fe-2d9d-4490-a5b3-6d9bf041e36f",
            type="deposit",
            amount=Decimal(10),
            currency="MXN",
        ),
    )
    await wait_event(lambda: has_instruction(sandbox_client, result.id), timeout=5)

    result = await get_transaction(sandbox_client, result.id)

    assert result.instruction.type == "instruction_file"
    assert result.instruction.file_url == "http://fake.url"


async def main():
    await asyncio.gather(
        run_paycash_deposit(),
        # run_paycash_sandbox_deposit(),
    )


if __name__ == "__main__":
    asyncio.run(main())
